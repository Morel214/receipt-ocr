"""Telegram handlers for tenant receipt bots (photo intake, rich preview, /edit, inline confirm/reject, and CSV/text export).

All bot, delivery mode, and destination webhook configuration is managed via the Web UI.
"""

import asyncio
from datetime import datetime
import html
import io
import json
import logging
from pathlib import Path
import re
import time
import uuid
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ocr_hub import config
from ocr_hub.repositories import jobs_repo, receipts_repo, tenants_repo
from ocr_hub.services import export_service, queue_service

logger = logging.getLogger(__name__)

# Per-(tenant_id, chat_id) batch aggregation state
_batch_state: dict[tuple[int, int], dict[str, Any]] = {}
_pending_tasks: dict[tuple[int, int], asyncio.Task] = {}
_batch_busy: dict[tuple[int, int], bool] = {}

_SOURCE_ICONS = {
    "cache": "⚡",
    "llm": "🆕",
    "rule": "🏷️",
    "user": "✏️",
}
_EDIT_CMD_STRIP_RE = re.compile(r"^/edit(?:@[A-Za-z0-9_]+)?\s*", flags=re.IGNORECASE)
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


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


def _extract_job_items(job: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract parsed line items from ``items_json`` or ``ocr_json``."""
    if job.get("items_json"):
        try:
            parsed = json.loads(job["items_json"])
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
    if job.get("ocr_json"):
        try:
            ocr_obj = json.loads(job["ocr_json"])
            if isinstance(ocr_obj, dict) and isinstance(ocr_obj.get("items"), list):
                return ocr_obj["items"]
        except Exception:
            pass
    return []


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
    items_count = len(_extract_job_items(job))
    items_tag = f" ({items_count} items)" if items_count else ""
    return f"#{job['id']} · {store} · {date} · {total_str} {currency}{items_tag}{dup}{review}{webhook_err}"


def build_job_inline_keyboard(job_id: int) -> InlineKeyboardMarkup:
    """Build mobile one-tap Confirm / Reject inline keyboard buttons for a receipt preview."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"✅ Confirm #{job_id}", callback_data=f"confirm:{job_id}"),
                InlineKeyboardButton(f"🗑️ Reject #{job_id}", callback_data=f"reject:{job_id}"),
            ]
        ]
    )


def build_batch_inline_keyboard(batch_id: str, count: int) -> InlineKeyboardMarkup:
    """Build batch-level Confirm All / Reject All inline buttons for multi-photo uploads."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"✅ Confirm All ({count})", callback_data=f"confirm_batch:{batch_id}"
                ),
                InlineKeyboardButton(
                    f"🗑️ Reject All ({count})", callback_data=f"reject_batch:{batch_id}"
                ),
            ]
        ]
    )


def render_job_preview(job: dict[str, Any], max_items: int = 45) -> str:
    """Render a rich pre-confirmation receipt preview with automatic total-sum verification."""
    job_id = job["id"]
    currency = (job.get("currency") or "PLN").strip()
    items = _extract_job_items(job)
    receipt_total = (
        round(float(job["total_amount"]), 2)
        if isinstance(job.get("total_amount"), (int, float))
        else 0.0
    )
    items_sum = round(sum(float(it.get("total_price") or 0.0) for it in items), 2)

    lines: list[str] = [f"🧾 {render_job_summary(job)}"]

    if job.get("is_duplicate"):
        lines.append("⚠️ Possible duplicate of an already confirmed receipt!")

    if not items:
        lines.append("⚠️ No line items were extracted from this photo.")
    else:
        diff = round(items_sum - receipt_total, 2)
        if abs(diff) > 0.05:
            lines.append(
                f"⚠️ Sum mismatch: items sum ({items_sum:.2f} {currency}) "
                f"!= receipt total ({receipt_total:.2f} {currency}, diff {diff:+.2f}) — check items below!"
            )
        else:
            lines.append(f"✅ Sum check OK ({items_sum:.2f} {currency} · {len(items)} items)")

        lines.append("")
        show_raw_subline = len(items) <= 25
        for idx, item in enumerate(items[:max_items], start=1):
            raw_name = str(item.get("name") or "").strip()
            clean = str(item.get("clean_name") or raw_name or "?").strip()
            subcat = item.get("subcategory") or "—"
            qty = float(item.get("quantity") if item.get("quantity") is not None else 1.0)
            unit = str(item.get("unit") or "pcs")
            unit_price = float(item.get("unit_price") or 0.0)
            total_price = float(item.get("total_price") or 0.0)
            icon = _SOURCE_ICONS.get(str(item.get("match_source") or "llm"), "🆕")
            lines.append(
                f"{idx}. {clean} [{subcat}] · {qty:g} {unit} × {unit_price:.2f} = {total_price:.2f} {currency} {icon}"
            )
            if show_raw_subline and raw_name and raw_name.lower() != clean.lower():
                lines.append(f"   ↳ {raw_name}")

        if len(items) > max_items:
            lines.append(f"… and {len(items) - max_items} more item(s).")

    if job.get("status") in queue_service.CONFIRMABLE_STATUSES:
        lines.append("")
        lines.append(
            f"✏️ Fix item: /edit {job_id} <no> name=... price=... qty=... subcat=... (or 'delete')"
        )
        lines.append(f"✏️ Fix header: /edit {job_id} store=... date=YYYY-MM-DD total=...")

    return "\n".join(lines)


def render_pending_list(jobs: list[dict[str, Any]], limit: int = 10) -> str:
    """Render a list of open jobs for a Telegram message."""
    if not jobs:
        return "No pending receipts."
    lines = [
        "🧾 Pending receipts (use /items <id>, /edit <id> ..., /confirm <id|all> or /reject <id|all>):"
    ]
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


def _format_confirm_summary(outcome: dict[str, Any]) -> str:
    """Build a concise post-confirmation summary across all enabled delivery modes."""
    modes = outcome.get("delivery_modes") or []
    lines = [
        f"✅ Confirmed receipt #{outcome['job_id']} "
        f"({outcome['store_name']} · {outcome['total_amount']:.2f} {outcome['currency']})"
    ]
    if outcome.get("saved_to_hub_db"):
        lines.append(f"• Hub DB: saved as receipt #{outcome['hub_receipt_id']}")
    if "webhook" in modes:
        if outcome.get("webhook_delivered"):
            lines.append(f"• Webhook: sent JSON (HTTP {outcome['webhook_status_code']})")
        else:
            lines.append("• Webhook: skipped (no destination URL configured)")
    if "telegram_text" in modes:
        lines.append("• Telegram Text: copyable table sent below")
    if "telegram_csv" in modes:
        lines.append("• Telegram CSV: file sent below")
    return "\n".join(lines)


async def _deliver_telegram_outputs(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    outcome: dict[str, Any],
) -> None:
    """Deliver post-confirmation copyable text and/or CSV file in Telegram when enabled."""
    modes = outcome.get("delivery_modes") or []
    result_dict = outcome.get("result")
    if not isinstance(result_dict, dict):
        return

    if "telegram_text" in modes:
        copy_text = export_service.format_receipt_copyable_text(result_dict)
        escaped = html.escape(copy_text)
        if len(escaped) <= 3850:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"<pre>{escaped}</pre>",
                parse_mode=ParseMode.HTML,
            )
        else:
            txt_name = export_service.build_receipt_csv_filename(result_dict).replace(
                ".csv", ".txt"
            )
            await context.bot.send_document(
                chat_id=chat_id,
                document=io.BytesIO(copy_text.encode("utf-8")),
                filename=txt_name,
                caption="📋 Copyable receipt CSV text",
            )

    if "telegram_csv" in modes:
        csv_bytes = export_service.format_receipts_csv_bytes([result_dict])
        csv_filename = export_service.build_receipt_csv_filename(result_dict)
        await context.bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(csv_bytes),
            filename=csv_filename,
            caption=f"📄 {csv_filename}",
        )


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
    """Debounce batch OCR so multiple photos sent quickly are grouped cleanly."""
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
    """OCR all jobs in ``batch_id`` and send rich preview card(s) with inline Confirm/Reject buttons."""
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

    for job in processed:
        await context.bot.send_message(
            chat_id=chat_id,
            text=render_job_preview(job),
            reply_markup=build_job_inline_keyboard(int(job["id"])),
        )

    if len(processed) > 1:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📦 Batch processed: {len(processed)} receipts ready for review.",
            reply_markup=build_batch_inline_keyboard(batch_id, len(processed)),
        )

    if failed_jobs:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Failed to read: " + ", ".join(f"#{job['id']}" for job in failed_jobs),
        )


HELP_TEXT = (
    "🤖 <b>Receipt OCR Bot</b>\n\n"
    "📸 Send one or more receipt photos to extract, verify, and classify line items.\n\n"
    "📄 <b>Commands</b>\n"
    "/pending — list pending receipts\n"
    "/items &lt;id&gt; — show full receipt preview &amp; sum check\n"
    "/edit &lt;id&gt; &lt;no&gt; name=... price=... qty=... subcat=... — fix an item before confirm\n"
    "/edit &lt;id&gt; &lt;no&gt; delete — remove a misread item\n"
    "/edit &lt;id&gt; store=... date=YYYY-MM-DD total=... — fix receipt header (or total=sum)\n"
    "/confirm &lt;id|all&gt; — confirm receipt(s) and deliver outputs\n"
    "/reject &lt;id|all&gt; — reject and delete receipt(s)\n"
    "/export [YYYY-MM | id | all] — export saved Hub DB receipts as CSV\n"
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
    """Show full preview (with total-sum check and inline buttons) for a receipt job."""
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

    markup = (
        build_job_inline_keyboard(job_id)
        if job.get("status") in queue_service.CONFIRMABLE_STATUSES
        else None
    )
    await update.message.reply_text(render_job_preview(job), reply_markup=markup)


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Edit a pending receipt's header or line item before confirming."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    if not is_allowed_chat(tenant, update.effective_chat.id):
        return

    raw_msg = update.message.text if isinstance(update.message.text, str) else ""
    stripped = _EDIT_CMD_STRIP_RE.sub("", raw_msg, count=1).strip()
    if not stripped and context.args:
        stripped = " ".join(context.args).strip()

    parts = stripped.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "• /edit <id> <item_no> name=jajka price=9.99 qty=1 subcat=eggs\n"
            "• /edit <id> <item_no> delete\n"
            "• /edit <id> store=Biedronka date=2026-10-28 total=54.30"
        )
        return

    try:
        job_id = int(parts[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("First argument must be the receipt ID, e.g. /edit 1 ...")
        return

    edit_spec = parts[1].strip()
    try:
        updated_job = await asyncio.to_thread(
            queue_service.edit_job_before_confirm,
            tenant["id"],
            job_id,
            edit_spec,
        )
    except ValueError as exc:
        await update.message.reply_text(f"❌ Edit failed: {exc}")
        return

    await update.message.reply_text(
        "✏️ Updated receipt preview:\n\n" + render_job_preview(updated_job),
        reply_markup=build_job_inline_keyboard(job_id),
    )


async def cmd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Confirm one job or all pending jobs and deliver across configured delivery_modes."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    if not is_allowed_chat(tenant, chat_id):
        return

    selector, value = parse_job_selector(context.args[0] if context.args else "")
    try:
        if selector == "single" and value is not None:
            outcome = await asyncio.to_thread(queue_service.confirm_job, tenant["id"], value)
            await update.message.reply_text(_format_confirm_summary(outcome))
            await _deliver_telegram_outputs(chat_id, context, outcome)
        elif selector == "all":
            outcomes = await asyncio.to_thread(queue_service.confirm_all, tenant["id"])
            await update.message.reply_text(
                f"✅ Confirmed and processed {len(outcomes)} receipt(s)."
            )
            for outcome in outcomes:
                await _deliver_telegram_outputs(chat_id, context, outcome)
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


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Export saved Hub DB receipts for a month (YYYY-MM), single receipt ID, or 'all' as CSV."""
    tenant = _get_tenant(context)
    if tenant is None or not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    if not is_allowed_chat(tenant, chat_id):
        return

    arg = context.args[0].strip() if context.args else datetime.now().strftime("%Y-%m")
    tenant_id = int(tenant["id"])

    if arg.lower() == "all":
        receipts = receipts_repo.list_receipts(
            tenant_id=tenant_id, limit=5000, include_items=True
        )
        filename = "receipts_all.csv"
        label = "all saved receipts"
    elif _MONTH_RE.match(arg):
        receipts = receipts_repo.list_receipts(
            tenant_id=tenant_id, month=arg, limit=2000, include_items=True
        )
        filename = f"receipts_{arg}.csv"
        label = f"month {arg}"
    elif arg.lstrip("#").isdigit():
        rec_id = int(arg.lstrip("#"))
        single = receipts_repo.get_receipt(rec_id, tenant_id=tenant_id)
        receipts = [single] if single is not None else []
        filename = (
            export_service.build_receipt_csv_filename(single)
            if single is not None
            else f"receipt_{rec_id}.csv"
        )
        label = f"receipt #{rec_id}"
    else:
        await update.message.reply_text(
            "Usage: /export [YYYY-MM | receipt_id | all]\nExample: /export 2026-10"
        )
        return

    if not receipts:
        hub_enabled = "hub_db" in (tenant.get("delivery_modes") or [])
        if not hub_enabled:
            await update.message.reply_text(
                "ℹ️ No saved receipts in Hub DB. Enable 'Save to Hub DB (hub_db)' in the Web Dashboard to use /export."
            )
        else:
            await update.message.reply_text(f"ℹ️ No saved receipts found for {label}.")
        return

    csv_bytes = export_service.format_receipts_csv_bytes(receipts)
    await context.bot.send_document(
        chat_id=chat_id,
        document=io.BytesIO(csv_bytes),
        filename=filename,
        caption=f"📊 Exported {len(receipts)} receipt(s) ({label})",
    )


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


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle one-tap inline Confirm / Reject button presses on receipt previews."""
    query = update.callback_query
    if query is None:
        return

    tenant = _get_tenant(context)
    chat = update.effective_chat
    if tenant is None or chat is None:
        await query.answer()
        return

    chat_id = chat.id
    if not is_allowed_chat(tenant, chat_id):
        await query.answer("Unauthorized chat.", show_alert=True)
        return

    await query.answer()
    data = (query.data or "").strip()
    if ":" not in data:
        return

    action, raw_target = data.split(":", 1)
    try:
        if action == "confirm":
            job_id = int(raw_target)
            outcome = await asyncio.to_thread(queue_service.confirm_job, tenant["id"], job_id)
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id, text=_format_confirm_summary(outcome)
            )
            await _deliver_telegram_outputs(chat_id, context, outcome)
        elif action == "reject":
            job_id = int(raw_target)
            ok = await asyncio.to_thread(queue_service.reject_job, tenant["id"], job_id)
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            msg = (
                f"🗑️ Rejected and deleted receipt #{job_id}."
                if ok
                else f"Receipt #{job_id} not found."
            )
            await context.bot.send_message(chat_id=chat_id, text=msg)
        elif action == "confirm_batch":
            outcomes = await asyncio.to_thread(
                queue_service.confirm_all, tenant["id"], raw_target
            )
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Confirmed and processed {len(outcomes)} receipt(s).",
            )
            for outcome in outcomes:
                await _deliver_telegram_outputs(chat_id, context, outcome)
        elif action == "reject_batch":
            rejected = await asyncio.to_thread(
                queue_service.reject_all, tenant["id"], raw_target
            )
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🗑️ Rejected {len(rejected)} receipt(s).",
            )
    except (ValueError, RuntimeError) as exc:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Action failed: {exc}")


def register_handlers(application: Application) -> None:
    """Attach photo, preview inline buttons, /edit, /export, and queue handlers to a tenant's bot."""
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("pending", cmd_pending))
    application.add_handler(CommandHandler("items", cmd_items))
    application.add_handler(CommandHandler("edit", cmd_edit))
    application.add_handler(CommandHandler("confirm", cmd_confirm))
    application.add_handler(CommandHandler("reject", cmd_reject))
    application.add_handler(CommandHandler("export", cmd_export))
    application.add_handler(CommandHandler("history", cmd_history))
