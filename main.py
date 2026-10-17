"""Amaya — multi-purpose Discord bot (order queue, deliveries, sticky messages,
Roblox group eligibility, monitoring form, quick math).

Run:   python main.py
"""
import asyncio
import importlib
import logging
import math
import os
import re
import sys
import time
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

import database  # noqa: E402
from buttons import OrderButtons  # noqa: E402
from keepalive import start_keepalive  # noqa: E402
from monitoring import MonitorFormView  # noqa: E402
from sticky_data import load_sticky_data, save_sticky_data  # noqa: E402
from utils import js_num  # noqa: E402

log = logging.getLogger("amaya")
BASE = Path(__file__).resolve().parent

MATH_RE = re.compile(
    r"^amaya\s+(-?\d+(?:\.\d+)?)\s*([+\-*/])\s*(-?\d+(?:\.\d+)?)$", re.IGNORECASE | re.ASCII
)


# ================= SCAN HELPERS =================
def extract_game_pass_id(text):
    if not text:
        return None
    s = str(text).strip()
    if re.fullmatch(r"\d+", s, re.ASCII):
        return s
    patterns = [
        r"game-pass/(\d+)",
        r"gamepass/(\d+)",
        r"game-passes/(\d+)",
        r"/passes/(\d+)",
        r"\b(?:gp|gamepass|game-pass)\D*(\d{5,})\b",
        r"id=(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, s, re.IGNORECASE | re.ASCII)
        if m:
            return m.group(1)
    return None


def load_scan_module():
    """Optional drop-in: scan.py exposing `async run_scan(id) -> {"ok": bool, "content": str}`
    and (optionally) `extract_game_pass_id(text)`."""
    try:
        return importlib.import_module("scan")
    except ModuleNotFoundError:
        log.error("❌ scan.py not found — the `scan` feature is disabled")
    except Exception:
        log.exception("❌ Failed to load scan.py")
    return None


# ================= TREE (global slash-command error handler) =================
class AmayaTree(app_commands.CommandTree):
    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        log.error("❌ Interaction error: %r", error, exc_info=error)
        msg = "❌ There was an error executing this command!"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass


# ================= BOT =================
class AmayaBot(commands.Bot):
    def __init__(self, deploy_only: bool = False):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        client_id = os.getenv("CLIENT_ID")
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            tree_cls=AmayaTree,
            application_id=int(client_id) if client_id else None,
            help_command=None,
        )
        self.deploy_only = deploy_only
        self.session: aiohttp.ClientSession | None = None
        self.scan = None
        self.sticky_cooldowns: dict[int, float] = {}
        self.processed_messages: set[int] = set()
        self._tasks: set[asyncio.Task] = set()
        self._web_runner = None

    # ---------- startup ----------
    async def load_cogs(self):
        cogs_dir = BASE / "cogs"
        for file in sorted(cogs_dir.glob("*.py")):
            if file.name.startswith("_"):
                continue
            try:
                await self.load_extension(f"cogs.{file.stem}")
                log.info("✅ Loaded cog: %s", file.stem)
            except Exception:
                log.exception("❌ Failed to load cog %s", file.name)

    async def setup_hook(self):
        await self.load_cogs()
        if self.deploy_only:
            return

        try:
            await database.connect()
        except Exception as err:
            log.error("❌ MongoDB connection error: %s", err)
            sys.exit(1)

        self.session = aiohttp.ClientSession()
        self._web_runner = await start_keepalive()
        self.scan = load_scan_module()

        # persistent buttons (keep working after restarts)
        self.add_view(OrderButtons())
        self.add_view(MonitorFormView())

    async def close(self):
        if self.session:
            await self.session.close()
        if self._web_runner:
            await self._web_runner.cleanup()
        await super().close()

    # ---------- events ----------
    async def on_ready(self):
        log.info("✅ Logged in as %s", self.user)
        log.info("🆔 Bot user ID: %s", self.user.id)
        log.info("📊 Serving %s server(s)", len(self.guilds))

        try:
            name = os.getenv("ACTIVITY_NAME", "amaya")
            kind = os.getenv("BOT_ACTIVITY", "PLAYING").upper()
            types = {
                "PLAYING": discord.ActivityType.playing,
                "WATCHING": discord.ActivityType.watching,
                "LISTENING": discord.ActivityType.listening,
                "COMPETING": discord.ActivityType.competing,
                "STREAMING": discord.ActivityType.streaming,
            }
            atype = types.get(kind, discord.ActivityType.playing)
            await self.change_presence(
                activity=discord.Activity(type=atype, name=name), status=discord.Status.online
            )
            log.info("✅ Presence set: %s %s | status=online", kind, name)
        except Exception:
            log.exception("❌ Failed to set presence")

    async def on_shard_disconnect(self, shard_id):
        log.warning("⚠️ Shard %s disconnected", shard_id)

    async def on_shard_ready(self, shard_id):
        log.info("✅ Shard %s is ready", shard_id)

    async def on_shard_resume(self, shard_id):
        log.info("🔄 Shard %s resumed", shard_id)

    async def on_app_command_completion(self, interaction, command):
        # refresh sticky after any slash command except /sticky itself
        if command.qualified_name.split()[0] != "sticky":
            self.schedule_sticky_refresh(interaction.channel)

    # ---------- sticky ----------
    def schedule_sticky_refresh(self, channel, delay: float = 1.0):
        async def _later():
            await asyncio.sleep(delay)
            await self.refresh_sticky(channel)

        task = asyncio.create_task(_later())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def refresh_sticky(self, channel):
        if channel is None or not getattr(channel, "id", None) or not hasattr(channel, "send"):
            return

        data = load_sticky_data()
        sticky = data.get(str(channel.id))
        if not sticky:
            return

        now = time.time()
        if now - self.sticky_cooldowns.get(channel.id, 0) < 3:
            return
        self.sticky_cooldowns[channel.id] = now

        try:
            if sticky.get("messageId"):
                try:
                    old = await channel.fetch_message(int(sticky["messageId"]))
                    await old.delete()
                except Exception:
                    pass  # old sticky may already be gone

            new = await channel.send(
                sticky["content"], allowed_mentions=discord.AllowedMentions.none()
            )
            data[str(channel.id)]["messageId"] = str(new.id)
            save_sticky_data(data)
        except Exception:
            log.exception("❌ Sticky refresh error")

    # ---------- scan ----------
    async def handle_scan(self, message: discord.Message, input_text: str):
        try:
            if not self.scan or not hasattr(self.scan, "run_scan"):
                return await message.reply("❌ Scan command is not available right now.")
            result = await self.scan.run_scan(input_text)
            if not result or not result.get("ok"):
                return await message.reply(
                    (result or {}).get("content") or "❌ Error fetching game pass info."
                )
            return await message.reply(result["content"])
        except Exception:
            log.exception("❌ Scan error")
            return await message.reply("❌ Error fetching game pass info.")

    # ---------- messages ----------
    async def on_message(self, message: discord.Message):
        try:
            if message.author.bot:
                return

            content = message.content

            # ===== MATH FEATURE =====
            m = MATH_RE.match(content.strip())
            if m:
                a, op, b = float(m.group(1)), m.group(2), float(m.group(3))
                if op == "+":
                    result = a + b
                elif op == "-":
                    result = a - b
                elif op == "*":
                    result = a * b
                else:
                    if b == 0:
                        await message.reply("❌ Can't divide by zero.")
                        return
                    result = a / b

                # trim floating point noise (JS Math.round semantics: half rounds up)
                if math.isfinite(result):
                    result = math.floor(result * 10000 + 0.5) / 10000

                await message.reply(f" **{js_num(a)} {op} {js_num(b)} = {js_num(result)}**")
                self.schedule_sticky_refresh(message.channel)
                return

            # ===== SCAN FEATURE =====
            scan_input = None
            lowered = content.lower()

            if lowered == "scan" and message.reference:
                try:
                    replied = await message.channel.fetch_message(message.reference.message_id)
                    if replied.content:
                        scan_input = replied.content
                    if not scan_input and replied.embeds:
                        e = replied.embeds[0]
                        if e.url:
                            scan_input = e.url
                        if not scan_input and e.description:
                            scan_input = e.description
                        if not scan_input and e.title:
                            scan_input = e.title
                except Exception:
                    log.exception("❌ Reply fetch error")
                    return
            elif lowered.startswith("scan "):
                scan_input = content[5:].strip()

            if scan_input:
                finder = getattr(self.scan, "extract_game_pass_id", None) or extract_game_pass_id
                pass_id = finder(scan_input)
                if not pass_id:
                    return await message.reply("❌ Invalid Roblox game pass link or ID.")

                if message.id in self.processed_messages:
                    return
                self.processed_messages.add(message.id)
                asyncio.get_running_loop().call_later(10, self.processed_messages.discard, message.id)

                await self.handle_scan(message, pass_id)
                self.schedule_sticky_refresh(message.channel)
                return

            # ===== STICKY FEATURE =====
            await self.refresh_sticky(message.channel)
        except Exception:
            log.exception("❌ on_message handler crashed")


# ================= LOGIN =================
async def run():
    token = os.getenv("BOT_TOKEN")
    log.info("🔐 BOT_TOKEN exists: %s", bool(token))
    if not token:
        log.error("❌ Missing BOT_TOKEN in environment variables.")
        sys.exit(1)

    bot = AmayaBot()
    async with bot:
        try:
            log.info("🔄 Attempting to login to Discord...")
            await bot.start(token)
        except discord.LoginFailure as err:
            log.error("❌ LOGIN FAILED: %s", err)
            sys.exit(1)


if __name__ == "__main__":
    discord.utils.setup_logging(level=logging.INFO)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
