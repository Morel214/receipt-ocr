"""Telegram command and photo handlers for tenant bots."""

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from ocr_hub import config
from ocr_hub.repositories import jobs_repo, tenants_repo
from ocr_hub.services import queue_service, webhook_dispatcher

logger = logging.getLogger(__name__)

# Per-(tenant_id, chat_id) batch aggregation state
_batch_state: dict[tuple[int, int], dict[str, Any]] = {}
_pending_tasks: dict[tuple[int, int], asyncio.Task] = {}
_batch_busy: dict[tuple[int, int], bool] = {}


def _get_tenant(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    """Load the current tenant record associated with this bot instance."""
    tenant_id = context.application.bot_data.get("tenant_id")
    if tenant_id is None:
        return None
    return tenants_repo.get_tenant_by_id(int(tenant_id))


def is_allowed_chat(tenant: dict[str, Any], chat_id: int) -> bool:
    """Return True if ``chat_id`` is allowed to use this tenant's bot."""
    allowed = tenant.get("allowed_chat_ids_list") or []
    if not allowed:
        return True
    return int(chat_id) in allowed


def current_batch_id(tenant_id: int, chat_id: int, now: float | None = None) -> str:
    """Return the active batch ID for ``(tenant_id, chat_id)``, starting a new one after cooldown."""
    now = now if now is not None else time.time()
    key = (tenant_id, chat_id)
    state = _batch_state.get(key)
    cooldown = config.TELEGRAM_BATCH_COOLDOWN_SECONDS
    if state and (now - state["last_photo_at"]) < cooldown:
        state["last_photo_at"] = now
        return state["batch_id"]
    batch_id = uuid.uuid4().hex[:12]
    _batch_state[key] = {"batch_id": batch_id, "last_photo_at": now}
    return batch_id


def save_receipt_image_bytes(tenant_id: int, data: bytes, ext: str = "jpg") -> Path:
    """Persist a photo into the tenant's receipts upload directory."""
    tenant_dir = config.RECEIPTS_UPLOAD_DIR / f"tenant_{tenant_id}"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    filename = f"telegram_{uuid.uuid4().hex[:8]}.{ext}"
    path = tenant_dir / filename
    path.write_bytes(data)
    return path


def render_job_summary(job: dict[str, Any]) -> str:
    """Render a single job into a human-readable summary line."""
    store = job.get("store_name") or "?"
    date = job.get("transaction_date") or "?"
    total = job.get("total_amount")
    total_str = f"{total:.2f}" if isinstance(total, (int, float)) else "?"
    currency = job.get("currency") or ""
    dup = " [duplikat]" if job.get("is_duplicate") else ""
    review = " [do weryfikacji]" if job.get("status") == jobs_repo.NEEDS_REVIEW else ""
    webhook_err = " [błąd wysyłki webhooka]" if job.get("status") == jobs_repo.DELIVERY_FAILED else ""
    items_count = 0
    if job.get("items_json"):
        try:
            items_count = len(json.loads(job["items_json"]))
        except Exception:
            items_count = 0
    items_tag = f" ({items_count} poz.)" if items_count else ""
    return f"#{job['id']} · {store} · {date} · {total_str} {currency}{items_tag}{dup}{review}{webhook_err}"


def render_pending_list(jobs: list[dict[str, Any]], limit: int = 10) -> str:
    """Render a list of open jobs for a Telegram message."""
    if not jobs:
        return "Brak oczekujących paragonów."
    lines = ["🧾 Oczekujące paragony (użyj /items <id>, /confirm <id|all> lub /reject <id|all>):"]
    for job in jobs[:limit]:
        lines.append(f"• {render_job_summary(job)}")
    if len(jobs) > limit:
        lines.append(f"… oraz {len(jobs) - limit} więcej.")
    return "\n".join(lines)


def render_status(tenant_id: int) -> str:
    """Render an overview of queue statuses for a tenant."""
    labels = {
        jobs_repo.QUEUED: "w kolejce (queued)",
        jobs_repo.AWAITING_CONFIRMATION: "oczekuje na potwierdzenie",
        jobs_repo.NEEDS_REVIEW: "niska pewność OCR (review)",
        jobs_repo.DELIVERY_FAILED: "błąd dostarczenia webhooka",
        jobs_repo.CONFIRMED: "potwierdzone i wysłane",
        jobs_repo.FAILED: "błąd OCR",
    }
    lines = ["📊 Status kolejki paragonów:"]
    for status, label in labels.items():
        count = jobs_repo.count_by_status(tenant_id=tenant_id, status=status)
        lines.append(f"• {label}: {count}")
    return "\n".join(lines)


def parse_job_selector(arg: str) -> tuple[str, int | None]:
    """Parse the argument of /confirm or /reject."""
    if not arg:
        return ("none", None)
    stripped = arg.strip().lower()
    if stripped in ("all", "batch", "wszystkie"):
        return ("all", None)
    try:
        return ("single", int(stripped.lstrip("#")))
    except ValueError:
        return ("invalid", None)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle an incoming receipt photo: save, queue, and debounce batch OCR."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    if not is_allowed_chat(tenant, chat_id):
        logger.warning(
            "[handle_photo] Unauthorized chat_id=%s for tenant=%s", chat_id, tenant["name"]
        )
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()
    data = await file.download_as_bytearray()

    try:
        tenant_id = tenant["id"]
        batch_id = current_batch_id(tenant_id, chat_id)
        image_path = save_receipt_image_bytes(tenant_id, bytes(data), ext="jpg")
        filename = photo.file_unique_id or f"tg_{chat_id}_{int(time.time())}.jpg"

        jobs_repo.create_job(
            tenant_id=tenant_id,
            batch_id=batch_id,
            chat_id=str(chat_id),
            message_id=update.message.message_id,
            filename=filename,
            image_path=str(image_path),
        )
        _schedule_batch_processing(tenant_id, chat_id, batch_id, context)
    except Exception:
        logger.exception("[handle_photo] Failed to queue photo for tenant %s", tenant["name"])
        await update.message.reply_text("❌ Wystąpił błąd podczas zapisywania zdjęcia.")


def _schedule_batch_processing(
    tenant_id: int,
    chat_id: int,
    batch_id: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Debounce batch OCR so multiple photos sent quickly are grouped into one prompt."""
    key = (tenant_id, chat_id)
    pending = _pending_tasks.get(key)
    if pending and not pending.done() and not _batch_busy.get(key):
        pending.cancel()

    holder: dict[str, Any] = {}

    async def runner() -> None:
        try:
            await asyncio.sleep(config.TELEGRAM_BATCH_DEBOUNCE_SECONDS)
            _batch_busy[key] = True
            try:
                await process_batch_and_notify(tenant_id, batch_id, chat_id, context)
            finally:
                _batch_busy.pop(key, None)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[_schedule_batch_processing] Batch %s failed", batch_id)
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Wystąpił błąd podczas przetwarzania paragonu przez OCR.",
                )
            except Exception:
                pass
        finally:
            if _pending_tasks.get(key) is holder.get("task"):
                _pending_tasks.pop(key, None)

    task = asyncio.create_task(runner())
    holder["task"] = task
    _pending_tasks[key] = task


async def process_batch_and_notify(
    tenant_id: int,
    batch_id: str,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """OCR all jobs in ``batch_id`` and send a single confirmation summary."""
    processed = await asyncio.to_thread(queue_service.process_batch, tenant_id, batch_id)
    failed_jobs = jobs_repo.list_jobs(
        tenant_id=tenant_id, status=jobs_repo.FAILED, batch_id=batch_id
    )

    if not processed:
        if failed_jobs:
            details = "; ".join(
                f"#{j['id']} ({j.get('last_error') or 'błąd'})" for j in failed_jobs
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Nie udało się odczytać paragonów: {details}",
            )
            return
        await context.bot.send_message(
            chat_id=chat_id,
            text="ℹ️ Brak nowych paragonów do przetworzenia w tej partii.",
        )
        return

    text = render_pending_list(processed)
    if failed_jobs:
        text += "\n\n⚠️ Nie udało się odczytać: " + ", ".join(
            f"#{job['id']}" for job in failed_jobs
        )
    await context.bot.send_message(chat_id=chat_id, text=text)


HELP_TEXT = (
    "🤖 <b>Receipt OCR Hub — Twój Osobisty Bot Paragonowy</b>\n\n"
    "📸 <b>Jak używać?</b>\n"
    "Wyślij jedno lub więcej zdjęć paragonów. Bot odczyta produkty, wyczyści ich nazwy, "
    "przypisze kategorie i zapyta Cię o potwierdzenie przed wysyłką do Twojej bazy.\n\n"
    "🧾 <b>Kolejka paragonów</b>\n"
    "/pending — oczekujące paragony do decyzji\n"
    "/items &lt;id&gt; — podgląd odczytanych pozycji z paragonu\n"
    "/confirm &lt;id|all&gt; — zatwierdź i wyślij JSON do swojej bazy\n"
    "/reject &lt;id|all&gt; — odrzuć i usuń paragon\n"
    "/status — statystyki kolejki\n"
    "/history — ostatnie 10 zatwierdzonych paragonów\n\n"
    "⚙️ <b>Konfiguracja Twojej bazy i modelu AI</b>\n"
    "/my_config — pokaż Twój klucz API, webhook i ustawienia\n"
    "/set_webhook &lt;url&gt; [token] — ustaw adres docelowy dla wyników\n"
    "/test_webhook — wyślij testowy ping do swojej bazy\n"
    "/set_model &lt;openai|gemini&gt; &lt;model&gt; — zmień model OCR w locie\n"
    "/set_categories &lt;kat1, kat2, ...|default&gt; — ustaw własne podkategorie"
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message and configuration hint."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return
    webhook_info = (
        f"✅ Docelowy webhook: <code>{tenant['webhook_url']}</code>"
        if tenant.get("webhook_url")
        else "⚠️ Nie ustawiłeś jeszcze docelowej bazy! Użyj <code>/set_webhook &lt;url&gt; [token]</code>."
    )
    await update.message.reply_text(
        f"Cześć <b>{tenant['name']}</b>! (Twój Chat ID: <code>{update.effective_chat.id}</code>)\n"
        f"{webhook_info}\n\n{HELP_TEXT}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available commands."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show queue counts for this tenant."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return
    await update.message.reply_text(render_status(tenant["id"]))


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List open jobs awaiting confirmation."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return
    jobs = jobs_repo.list_open_jobs(tenant_id=tenant["id"])
    await update.message.reply_text(render_pending_list(jobs))


async def cmd_items(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inspect individual parsed items of a receipt job."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return
    if not context.args:
        await update.message.reply_text("Użycie: /items <job_id>")
        return
    try:
        job_id = int(context.args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("Podaj poprawny numer ID paragonu, np. /items 1")
        return

    job = jobs_repo.get_job(job_id, tenant_id=tenant["id"])
    if job is None:
        await update.message.reply_text(f"Paragon #{job_id} nie istnieje.")
        return

    items = json.loads(job["items_json"]) if job.get("items_json") else []
    header = f"🧾 {render_job_summary(job)}\n"
    if not items:
        await update.message.reply_text(header + "Brak odczytanych pozycji.")
        return

    lines = [header, "Pozycje:"]
    for idx, item in enumerate(items, start=1):
        subcat = item.get("subcategory") or "—"
        clean = item.get("clean_name") or item.get("name")
        qty = item.get("quantity", 1)
        total = item.get("total_price", 0.0)
        lines.append(
            f"{idx}. {clean} [{subcat}] · {qty:g}x · {float(total):.2f} {job.get('currency') or ''}"
        )
    await update.message.reply_text("\n".join(lines))


async def cmd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Confirm one job or all pending jobs and deliver to the tenant's webhook."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return

    selector, value = parse_job_selector(context.args[0] if context.args else "")
    try:
        if selector == "single" and value is not None:
            outcome = await asyncio.to_thread(queue_service.confirm_job, tenant["id"], value)
            if outcome["webhook_delivered"]:
                msg = (
                    f"✅ Potwierdzono paragon #{outcome['job_id']} "
                    f"({outcome['store_name']} · {outcome['total_amount']:.2f} {outcome['currency']}) "
                    f"i wysłano do Twojej bazy (HTTP {outcome['webhook_status_code']})."
                )
            else:
                msg = (
                    f"✅ Potwierdzono paragon #{outcome['job_id']} "
                    f"({outcome['store_name']} · {outcome['total_amount']:.2f} {outcome['currency']}).\n"
                    "ℹ️ Brak ustawionego webhooka (/set_webhook) — wynik zapisany tylko w historii huba."
                )
            await update.message.reply_text(msg)
        elif selector == "all":
            outcomes = await asyncio.to_thread(queue_service.confirm_all, tenant["id"])
            await update.message.reply_text(
                f"✅ Potwierdzono i przetworzono {len(outcomes)} paragon(ów)."
            )
        else:
            await update.message.reply_text("Użycie: /confirm <job_id | all>")
    except (ValueError, RuntimeError) as exc:
        await update.message.reply_text(f"❌ Nie udało się potwierdzić: {exc}")


async def cmd_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject one job or all open jobs for this tenant."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return

    selector, value = parse_job_selector(context.args[0] if context.args else "")
    if selector == "single" and value is not None:
        ok = await asyncio.to_thread(queue_service.reject_job, tenant["id"], value)
        if ok:
            await update.message.reply_text(f"🗑️ Odrzucono i usunięto paragon #{value}.")
        else:
            await update.message.reply_text(f"Paragon #{value} nie został znaleziony.")
    elif selector == "all":
        rejected = await asyncio.to_thread(queue_service.reject_all, tenant["id"])
        await update.message.reply_text(f"🗑️ Odrzucono {len(rejected)} paragon(ów).")
    else:
        await update.message.reply_text("Użycie: /reject <job_id | all>")


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the 10 most recently confirmed receipts for this tenant."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return

    confirmed = jobs_repo.list_jobs(tenant_id=tenant["id"], status=jobs_repo.CONFIRMED)[-10:]
    if not confirmed:
        await update.message.reply_text("Brak potwierdzonych paragonów w historii.")
        return
    await update.message.reply_text(
        "📜 Ostatnio potwierdzone paragony:\n"
        + "\n".join(f"• {render_job_summary(job)}" for job in confirmed)
    )


async def cmd_set_webhook(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Configure or clear the destination webhook URL and optional Bearer token."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Użycie:\n"
            "/set_webhook < https://twoja-baza.pl/webhook > [opcjonalny_bearer_token]\n"
            "Lub aby wyczyścić: /set_webhook clear"
        )
        return

    first_arg = context.args[0].strip()
    if first_arg.lower() in ("clear", "none", "off"):
        tenants_repo.update_tenant(tenant["id"], webhook_url=None, webhook_secret=None)
        await update.message.reply_text("🧹 Wyczyszczono ustawienia docelowego webhooka.")
        return

    if not (first_arg.startswith("http://") or first_arg.startswith("https://")):
        await update.message.reply_text("❌ Adres URL musiaczynać się od http:// lub https://")
        return

    secret = context.args[1].strip() if len(context.args) > 1 else tenant.get("webhook_secret")
    tenants_repo.update_tenant(tenant["id"], webhook_url=first_arg, webhook_secret=secret)
    secret_info = "ustawiony (Bearer)" if secret else "brak"
    await update.message.reply_text(
        f"✅ Zapisano docelowe miejsce wysyłki wyników:\n"
        f"• URL: {first_arg}\n"
        f"• Token autoryzacji: {secret_info}\n\n"
        "Możesz przetestować połączenie komendą /test_webhook"
    )


async def cmd_test_webhook(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a test POST request to the tenant's configured webhook URL."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return

    result = await asyncio.to_thread(webhook_dispatcher.send_test_webhook, tenant)
    if result["ok"]:
        await update.message.reply_text(
            f"✅ Połączenie z Twoją bazą działa! (HTTP {result['status_code']})\n"
            f"Odpowiedź: {result['detail']}"
        )
    else:
        await update.message.reply_text(
            f"❌ Test webhooka nie powiódł się (HTTP {result['status_code']}):\n{result['detail']}"
        )


async def cmd_set_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Change the cloud OCR provider and model for this tenant on the fly."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Użycie:\n"
            "• /set_model openai gpt-4o-mini\n"
            "• /set_model openai gpt-4o\n"
            "• /set_model gemini gemini-2.5-flash\n"
            "• /set_model default (przywraca domyślny model serwera)"
        )
        return

    if context.args[0].lower() == "default":
        tenants_repo.update_tenant(tenant["id"], ocr_provider=None, ocr_model=None)
        await update.message.reply_text(
            f"✅ Przywrócono domyślny model serwera ({config.OCR_PROVIDER} / {config.OCR_MODEL})."
        )
        return

    if len(context.args) < 2:
        await update.message.reply_text("Podaj dostawcę (openai lub gemini) oraz nazwę modelu.")
        return

    provider = context.args[0].strip().lower()
    model = context.args[1].strip()
    if provider not in ("openai", "gemini", "openrouter"):
        await update.message.reply_text("❌ Dostawca musi być jednym z: openai, gemini, openrouter.")
        return

    tenants_repo.update_tenant(tenant["id"], ocr_provider=provider, ocr_model=model)
    await update.message.reply_text(f"✅ Ustawiono model OCR: {provider} / {model}")


async def cmd_set_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Customize item classification subcategories for this tenant."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Użycie:\n"
            "/set_categories nabiał, mięso, warzywa, owoce, inne\n"
            "Lub aby przywrócić domyślne: /set_categories default"
        )
        return

    raw_text = " ".join(context.args).strip()
    if raw_text.lower() == "default":
        tenants_repo.update_tenant(tenant["id"], subcategories=None)
        await update.message.reply_text(
            f"✅ Przywrócono domyślne podkategorie Biometera:\n{', '.join(config.DEFAULT_SUBCATEGORIES)}"
        )
        return

    categories = [c.strip() for c in raw_text.split(",") if c.strip()]
    if not categories:
        await update.message.reply_text("❌ Podaj przynajmniej jedną podkategorię.")
        return

    tenants_repo.update_tenant(tenant["id"], subcategories=categories)
    await update.message.reply_text(
        f"✅ Zapisano własne podkategorie ({len(categories)}):\n{', '.join(categories)}"
    )


async def cmd_my_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the tenant's current settings, webhook URL, and personal REST API key."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return

    provider = tenant.get("ocr_provider") or f"{config.OCR_PROVIDER} (domyślny)"
    model = tenant.get("ocr_model") or f"{config.OCR_MODEL} (domyślny)"
    webhook = tenant.get("webhook_url") or "brak (ustaw przez /set_webhook)"
    has_secret = "tak" if tenant.get("webhook_secret") else "nie"
    subcats = ", ".join(tenant.get("subcategories") or config.DEFAULT_SUBCATEGORIES)

    text = (
        f"⚙️ <b>Konfiguracja profilu: {tenant['name']}</b>\n\n"
        f"🔑 <b>Twój API Key (do REST API):</b>\n<code>{tenant['api_key']}</code>\n\n"
        f"🌐 <b>Docelowy Webhook (Twoja baza):</b>\n<code>{webhook}</code>\n"
        f"🔒 <b>Bearer Token dla webhooka:</b> {has_secret}\n\n"
        f"🧠 <b>Silnik OCR:</b> <code>{provider}</code> / <code>{model}</code>\n"
        f"💱 <b>Domyślna waluta:</b> <code>{tenant.get('default_currency', 'PLN')}</code>\n"
        f"🏷️ <b>Podkategorie:</b> {subcats}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


def register_handlers(application: Application) -> None:
    """Attach all photo and command handlers to a tenant's Telegram Application."""
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("pending", cmd_pending))
    application.add_handler(CommandHandler("items", cmd_items))
    application.add_handler(CommandHandler("confirm", cmd_confirm))
    application.add_handler(CommandHandler("reject", cmd_reject))
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CommandHandler("set_webhook", cmd_set_webhook))
    application.add_handler(CommandHandler("test_webhook", cmd_test_webhook))
    application.add_handler(CommandHandler("set_model", cmd_set_model))
    application.add_handler(CommandHandler("set_categories", cmd_set_categories))
    application.add_handler(CommandHandler("my_config", cmd_my_config))
