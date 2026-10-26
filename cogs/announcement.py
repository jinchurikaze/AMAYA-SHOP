import logging
import os
from datetime import time as datetime_time, timedelta, timezone

import discord
from discord.ext import commands, tasks


log = logging.getLogger("amaya.announcement")
MANILA_TIME = timezone(timedelta(hours=8), name="Asia/Manila")
DAILY_POST_TIME = datetime_time(hour=8, minute=0, tzinfo=MANILA_TIME)


class DailyAnnouncement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not getattr(bot, "deploy_only", False):
            self.post_daily_announcement.start()

    def cog_unload(self):
        if self.post_daily_announcement.is_running():
            self.post_daily_announcement.cancel()

    async def _get_letters_channel(self) -> discord.TextChannel | None:
        channel_id = os.getenv("LETTERS_CHANNEL_ID", "").strip()
        if channel_id:
            try:
                channel_id_int = int(channel_id)
            except ValueError:
                log.error("LETTERS_CHANNEL_ID must be a Discord channel ID")
                return None

            channel = self.bot.get_channel(channel_id_int)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id_int)
                except discord.HTTPException:
                    log.exception("Could not fetch the configured letters channel")
                    return None
            if isinstance(channel, discord.TextChannel):
                return channel
            log.error("LETTERS_CHANNEL_ID does not point to a text channel")
            return None

        guild_id = os.getenv("GUILD_ID", "").strip()
        try:
            guild = self.bot.get_guild(int(guild_id))
        except ValueError:
            guild = None
        if guild is None:
            log.error("Set LETTERS_CHANNEL_ID or a valid GUILD_ID")
            return None

        channel = next(
            (item for item in guild.text_channels if item.name.casefold() == "letters"),
            None,
        )
        if channel is None:
            log.error("No text channel named #letters was found in GUILD_ID")
        return channel

    def _make_view(self) -> discord.ui.View | None:
        links = [
            ("available", os.getenv("LETTERS_AVAILABLE_URL", "").strip()),
            ("order here", os.getenv("LETTERS_ORDER_URL", "").strip()),
            ("ask us", os.getenv("LETTERS_ASK_URL", "").strip()),
        ]
        view = discord.ui.View(timeout=None)
        for label, url in links:
            if url.startswith(("https://", "http://")):
                view.add_item(
                    discord.ui.Button(
                        label=label,
                        style=discord.ButtonStyle.link,
                        url=url,
                    )
                )
        return view if view.children else None

    @tasks.loop(time=DAILY_POST_TIME)
    async def post_daily_announcement(self):
        channel = await self._get_letters_channel()
        if channel is None:
            return

        staff_role = None
        raw_role_id = os.getenv("LETTERS_STAFF_ROLE_ID", "").strip()
        if raw_role_id:
            try:
                staff_role = channel.guild.get_role(int(raw_role_id))
            except ValueError:
                log.error("LETTERS_STAFF_ROLE_ID must be a Discord role ID")
        if raw_role_id and staff_role is None:
            log.warning("Configured letters announcement staff role was not found")

        seller = None
        raw_seller_id = os.getenv("LETTERS_SELLER_USER_ID", "").strip()
        if raw_seller_id:
            try:
                seller = channel.guild.get_member(int(raw_seller_id))
            except ValueError:
                log.error("LETTERS_SELLER_USER_ID must be a Discord user ID")

        seller_text = f" {seller.mention}" if seller else ""
        staff_text = staff_role.mention if staff_role else "@staff"
        embed = discord.Embed(
            title="🐱 amaya is now open! ♡",
            description=(
                f"drop ur orders now{seller_text}\n"
                "click the order button below to order\n"
                f"ping {staff_text} for faster transaction\n"
                "no rush pls. happy shopping"
            ),
            color=0xD89A28,
        )

        allowed_mentions = discord.AllowedMentions(
            users=[seller] if seller else [],
            roles=[staff_role] if staff_role else [],
        )
        try:
            await channel.send(
                content=staff_role.mention if staff_role else None,
                embed=embed,
                view=self._make_view(),
                allowed_mentions=allowed_mentions,
            )
            log.info("Posted the daily announcement in #%s", channel.name)
        except discord.Forbidden:
            log.error("I cannot post the daily announcement in #%s", channel.name)
        except discord.HTTPException:
            log.exception("Failed to post the daily announcement in #%s", channel.name)

    @post_daily_announcement.before_loop
    async def before_post_daily_announcement(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(DailyAnnouncement(bot))

