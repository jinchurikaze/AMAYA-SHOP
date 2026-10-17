import logging
import os

from aiohttp import web
from datetime import datetime, timezone

log = logging.getLogger("amaya.keepalive")


async def start_keepalive() -> web.AppRunner:
    """Tiny web server for Render/Replit/UptimeRobot pings."""
    app = web.Application()

    async def index(_request):
        return web.Response(text="✅ Bot is running!")

    async def health(_request):
        return web.json_response(
            {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}
        )

    app.router.add_get("/", index)
    app.router.add_get("/health", health)

    port = int(os.getenv("PORT", "3000"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("🌐 Server is ready on port %s", port)
    return runner
