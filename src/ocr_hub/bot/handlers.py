"""Telegram handlers for tenant receipt bots (photo intake and queue confirmation only).

All bot & destination webhook configuration is managed via the Web UI.
"""

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
from ocr_hub.services import queue_service

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
    dup = " [duplicate]" if job.get("is_duplicate") else ""
    review = " [review]" if job.get("status") == jobs_repo.NEEDS_REVIEW else ""
    webhook_err = " [webhook failed]" if job.get("status") == jobs_repo.DELIVERY_FAILED else ""
    items_count = 0
    if job.get("items_json"):
        try:
            items_count = len(json.loads(job["items_json"]))
        except Exception:
            items_count = 0
    items_tag = f" ({items_count} items)" if items_count else ""
    return f"#{job['id']} · {store} · {date} · {total_str} {currency}{items_tag}{dup}{review}{webhook_err}"


def render_pending_list(jobs: list[dict[str, Any]], limit: int = 10) -> str:
    """Render a list of open jobs for a Telegram message."""
    if not jobs:
        return "No pending receipts."
    lines = ["🧾 Pending receipts (use /items <id>, /confirm <id|all> or /reject <id|all>):"]
    for job in jobs[:limit]:
        lines.append(f"• {render_job_summary(job)}")
    if len(jobs) > limit:
        lines.append(f"… and {len(jobs) - limit} more.")
    return "\n".join(lines)


def render_status(tenant_id: int) -> str:
    """Render an overview of queue statuses for a tenant."""
    labels = {
        jobs_repo.QUEUED: "queued",
        jobs_repo.AWAITING_CONFIRMATION: "awaiting confirmation",
        jobs_repo.NEEDS_REVIEW: "needs review",
        jobs_repo.DELIVERY_FAILED: "webhook delivery failed",
        jobs_repo.CONFIRMED: "confirmed & sent",
        jobs_repo.FAILED: "failed",
    }
    lines = ["📊 Queue status:"]
    for status, label in labels.items():
        count = jobs_repo.count_by_status(tenant_id=tenant_id, status=status)
        lines.append(f"• {label}: {count}")
    return "\n".join(lines)


def parse_job_selector(arg: str) -> tuple[str, int | None]:
    """Parse the argument of /confirm or /reject."""
    if not arg:
        return ("none", None)
    stripped = arg.strip().lower()
    if stripped in ("all", "batch"):
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
        await update.message.reply_text("❌ Failed to process incoming photo.")


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
                    text="❌ An error occurred while processing the receipt with OCR.",
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
                f"#{j['id']} ({j.get('last_error') or 'error'})" for j in failed_jobs
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Failed to parse receipts: {details}",
            )
            return
        await context.bot.send_message(
            chat_id=chat_id,
            text="ℹ️ No new receipts found to process in this batch.",
        )
        return

    text = render_pending_list(processed)
    if failed_jobs:
        text += "\n\n⚠️ Failed to read: " + ", ".join(
            f"#{job['id']}" for job in failed_jobs
        )
    await context.bot.send_message(chat_id=chat_id, text=text)


HELP_TEXT = (
    "🤖 <b>Receipt OCR Bot</b>\n\n"
    "📸 Send one or more receipt photos to extract and classify line items.\n\n"
    "📄 <b>Commands</b>\n"
    "/pending — list pending receipts\n"
    "/items &lt;id&gt; — inspect extracted items for a receipt\n"
    "/confirm &lt;id|all&gt; — confirm receipt(s) and send JSON to your webhook\n"
    "/reject &lt;id|all&gt; — reject and delete receipt(s)\n"
    "/status — queue overview\n"
    "/history — last 10 confirmed receipts"
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return
    await update.message.reply_text(
        f"Hi <b>{tenant['name']}</b>! (Chat ID: <code>{update.effective_chat.id}</code>)\n\n"
        f"{HELP_TEXT}",
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
        await update.message.reply_text("Usage: /items <job_id>")
        return
    try:
        job_id = int(context.args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("Please provide a valid receipt ID, e.g. /items 1")
        return

    job = jobs_repo.get_job(job_id, tenant_id=tenant["id"])
    if job is None:
        await update.message.reply_text(f"Receipt #{job_id} not found.")
        return

    items = json.loads(job["items_json"]) if job.get("items_json") else []
    header = f"🧾 {render_job_summary(job)}\n"
    if not items:
        await update.message.reply_text(header + "No line items found.")
        return

    lines = [header, "Items:"]
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
    """Confirm one job or all pending jobs and deliver JSON to the tenant's webhook."""
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
                    f"✅ Confirmed receipt #{outcome['job_id']} "
                    f"({outcome['store_name']} · {outcome['total_amount']:.2f} {outcome['currency']}) "
                    f"and sent JSON to your destination webhook (HTTP {outcome['webhook_status_code']})."
                )
            else:
                msg = (
                    f"✅ Confirmed receipt #{outcome['job_id']} "
                    f"({outcome['store_name']} · {outcome['total_amount']:.2f} {outcome['currency']}).\n"
                    "ℹ️ No destination webhook configured in the Web Dashboard."
                )
            await update.message.reply_text(msg)
        elif selector == "all":
            outcomes = await asyncio.to_thread(queue_service.confirm_all, tenant["id"])
            await update.message.reply_text(
                f"✅ Confirmed and processed {len(outcomes)} receipt(s)."
            )
        else:
            await update.message.reply_text("Usage: /confirm <job_id | all>")
    except (ValueError, RuntimeError) as exc:
        await update.message.reply_text(f"❌ Could not confirm: {exc}")


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
            await update.message.reply_text(f"🗑️ Rejected and deleted receipt #{value}.")
        else:
            await update.message.reply_text(f"Receipt #{value} not found.")
    elif selector == "all":
        rejected = await asyncio.to_thread(queue_service.reject_all, tenant["id"])
        await update.message.reply_text(f"🗑️ Rejected {len(rejected)} receipt(s).")
    else:
        await update.message.reply_text("Usage: /reject <job_id | all>")


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the 10 most recently confirmed receipts for this tenant."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return

    confirmed = jobs_repo.list_jobs(tenant_id=tenant["id"], status=jobs_repo.CONFIRMED)[-10:]
    if not confirmed:
        await update.message.reply_text("No confirmed receipts yet.")
        return
    await update.message.reply_text(
        "📜 Recently confirmed receipts:\n"
        + "\n".join(f"• {render_job_summary(job)}" for job in confirmed)
    )


def register_handlers(application: Application) -> None:
    """Attach photo and queue confirmation handlers to a tenant's Telegram Application."""
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("pending", cmd_pending))
    application.add_handler(CommandHandler("items", cmd_items))
    application.add_handler(CommandHandler("confirm", cmd_confirm))
    application.add_handler(CommandHandler("reject", cmd_reject))
    application.add_handler(CommandHandler("history", cmd_history))
