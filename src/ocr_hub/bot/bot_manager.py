"""Dynamic Multi-Bot Manager for running multiple Telegram bots concurrently in one asyncio loop."""

import logging
from typing import Any

from telegram.ext import Application

from ocr_hub import config
from ocr_hub.bot.handlers import register_handlers
from ocr_hub.repositories import tenants_repo

logger = logging.getLogger(__name__)


class BotManager:
    """Manages the lifecycle of multiple tenant Telegram bot instances at runtime."""

    def __init__(self) -> None:
        self._apps: dict[int, Application] = {}
        self._tokens: dict[int, str] = {}

    def running_tenant_ids(self) -> list[int]:
        """Return list of tenant IDs whose Telegram bots are currently active."""
        return list(self._apps.keys())

    def is_running(self, tenant_id: int) -> bool:
        """Return True if a bot is currently running for ``tenant_id``."""
        return tenant_id in self._apps

    def build_tenant_application(self, tenant: dict[str, Any]) -> Application:
        """Build a configured ``telegram.ext.Application`` for a single tenant."""
        token = (tenant.get("telegram_bot_token") or "").strip()
        if not token:
            raise ValueError(f"Tenant {tenant['name']} does not have a telegram_bot_token")
        application = Application.builder().token(token).build()
        application.bot_data["tenant_id"] = tenant["id"]
        application.bot_data["tenant_name"] = tenant["name"]
        register_handlers(application)
        return application

    async def start_bot_for_tenant(self, tenant: dict[str, Any]) -> bool:
        """Start (or restart) a non-blocking polling bot for ``tenant``."""
        tenant_id = int(tenant["id"])
        token = (tenant.get("telegram_bot_token") or "").strip()
        is_active = bool(tenant.get("is_active", True))

        if not token or not is_active:
            await self.stop_bot_for_tenant(tenant_id)
            return False

        if tenant_id in self._apps and self._tokens.get(tenant_id) == token:
            logger.debug("[BotManager] Bot for tenant %s is already running.", tenant["name"])
            return True

        if tenant_id in self._apps:
            await self.stop_bot_for_tenant(tenant_id)

        try:
            app = self.build_tenant_application(tenant)
            await app.initialize()
            await app.start()
            if app.updater is not None:
                await app.updater.start_polling(
                    poll_interval=config.TELEGRAM_POLL_INTERVAL_SECONDS,
                    drop_pending_updates=False,
                )
            self._apps[tenant_id] = app
            self._tokens[tenant_id] = token
            logger.info(
                "[BotManager] Started Telegram bot for tenant '%s' (id=%s)",
                tenant["name"],
                tenant_id,
            )
            return True
        except Exception:
            logger.exception(
                "[BotManager] Failed to start Telegram bot for tenant '%s' (id=%s)",
                tenant["name"],
                tenant_id,
            )
            return False

    async def stop_bot_for_tenant(self, tenant_id: int) -> None:
        """Gracefully stop and remove a tenant's running Telegram bot."""
        app = self._apps.pop(tenant_id, None)
        self._tokens.pop(tenant_id, None)
        if app is None:
            return

        try:
            if app.updater is not None and app.updater.running:
                await app.updater.stop()
            if app.running:
                await app.stop()
            await app.shutdown()
            logger.info("[BotManager] Stopped Telegram bot for tenant_id=%s", tenant_id)
        except Exception:
            logger.exception("[BotManager] Error stopping bot for tenant_id=%s", tenant_id)

    async def start_all_from_db(self) -> int:
        """Load all active tenants with bot tokens from SQLite and start their bots."""
        tenants = tenants_repo.list_tenants(only_active=True)
        started = 0
        for tenant in tenants:
            if tenant.get("telegram_bot_token"):
                ok = await self.start_bot_for_tenant(tenant)
                if ok:
                    started += 1
        logger.info("[BotManager] Active Telegram bots running: %d", started)
        return started

    async def stop_all(self) -> None:
        """Stop all running Telegram bots cleanly."""
        for tenant_id in list(self._apps.keys()):
            await self.stop_bot_for_tenant(tenant_id)


# Singleton instance shared between FastAPI lifespan and Admin endpoints
bot_manager = BotManager()
