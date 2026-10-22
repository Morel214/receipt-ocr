"""Command-line interface for Receipt OCR Hub."""

import argparse
import logging
import uvicorn

from ocr_hub import config
from ocr_hub.db.schema import init_db
from ocr_hub.repositories import tenants_repo


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the FastAPI gateway + Telegram Multi-Bot Manager."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    uvicorn.run(
        "ocr_hub.api.app:app",
        host=args.host or config.API_HOST,
        port=args.port or config.API_PORT,
        reload=args.reload,
    )


def cmd_init_db(_args: argparse.Namespace) -> None:
    """Initialize SQLite database tables."""
    init_db()
    print(f"Database initialized at: {config.DB_PATH}")


def cmd_add_tenant(args: argparse.Namespace) -> None:
    """Register a new user/friend and print their generated API key."""
    init_db()
    chat_ids = [
        int(x.strip())
        for x in (args.chat_ids or "").split(",")
        if x.strip().lstrip("-").isdigit()
    ]
    tenant = tenants_repo.create_tenant(
        name=args.name,
        telegram_bot_token=args.bot_token,
        allowed_chat_ids=chat_ids,
        webhook_url=args.webhook_url,
        webhook_secret=args.webhook_secret,
        default_currency=args.currency,
    )
    print(f"✅ Created tenant '{tenant['name']}' (id={tenant['id']})")
    print(f"🔑 API Key:      {tenant['api_key']}")
    print(f"🤖 Bot Token:    {'configured' if tenant.get('telegram_bot_token') else 'none'}")
    print(f"🌐 Webhook URL:  {tenant.get('webhook_url') or 'not set (user can set via /set_webhook)'}")


def cmd_list_tenants(_args: argparse.Namespace) -> None:
    """List all registered users/bots."""
    init_db()
    tenants = tenants_repo.list_tenants()
    if not tenants:
        print("No tenants registered yet. Use 'ocr-hub add-tenant --name ...' to add one.")
        return
    for t in tenants:
        bot_flag = "🤖 Bot configured" if t.get("telegram_bot_token") else "🔌 API only"
        wh_flag = t.get("webhook_url") or "no webhook"
        print(
            f"• #{t['id']} {t['name']} | {bot_flag} | API Key: {t['api_key']} | Webhook: {wh_flag}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="ocr-hub",
        description="Receipt OCR Hub — Multi-tenant OCR API & Telegram Bot Manager",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser("serve", help="Run the FastAPI server and Telegram BotManager")
    serve_p.add_argument("--host", default=None, help="Bind host (default from .env)")
    serve_p.add_argument("--port", type=int, default=None, help="Bind port (default from .env)")
    serve_p.add_argument("--reload", action="store_true", help="Enable auto-reload for dev")
    serve_p.set_defaults(func=cmd_serve)

    init_p = sub.add_parser("init-db", help="Initialize the SQLite database")
    init_p.set_defaults(func=cmd_init_db)

    add_p = sub.add_parser("add-tenant", help="Add a new user/friend and generate their API key")
    add_p.add_argument("--name", required=True, help="Unique name of the user/friend")
    add_p.add_argument("--bot-token", default=None, help="Telegram bot token from @BotFather")
    add_p.add_argument("--chat-ids", default="", help="Comma-separated allowed Telegram chat IDs")
    add_p.add_argument("--webhook-url", default=None, help="Destination webhook URL for results")
    add_p.add_argument("--webhook-secret", default=None, help="Bearer secret for the webhook")
    add_p.add_argument("--currency", default="PLN", help="Default currency (PLN, EUR, USD)")
    add_p.set_defaults(func=cmd_add_tenant)

    list_p = sub.add_parser("list-tenants", help="List all registered users and their API keys")
    list_p.set_defaults(func=cmd_list_tenants)

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
