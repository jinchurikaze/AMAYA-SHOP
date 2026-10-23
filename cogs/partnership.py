import os
import re
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db


INVITE_RE = re.compile(
    r"https?://(?:www\.)?(?:discord\.gg/[A-Za-z0-9-]+|discord(?:app)?\.com/invite/[A-Za-z0-9-]+)",
    re.IGNORECASE,
)


class Partnership(commands.GroupCog, name="partnership", description="Track partnership posts"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="list", description="Show recently tracked partnership posts")
    @app_commands.describe(limit="Number of recent posts to show")
    async def list_(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10] = 10):
        entries = await get_db()["partnership_posts"].find(
            {"guild_id": str(interaction.guild_id)}
        ).sort("created_at", -1).to_list(length=limit)
        if not entries:
            return await interaction.response.send_message(
                "No partnership posts have been tracked yet.", ephemeral=True
            )

        lines = []
        for entry in entries:
            timestamp = entry.get("created_at")
            stamp = discord.utils.format_dt(timestamp, style="R") if timestamp else "unknown time"
            post_url = (
                f"https://discord.com/channels/{entry.get('guild_id')}/"
                f"{entry.get('channel_id')}/{entry.get('message_id')}"
            )
            lines.append(
                f"• {entry.get('invite_url', 'link unavailable')} — "
                f"<@{entry.get('manager_id')}> · {stamp} · [post]({post_url})"
            )
        await interaction.response.send_message(
            "\n".join(lines),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return

        channel_id = os.getenv("PARTNERSHIP_CHANNEL_ID")
        role_id = os.getenv("PARTNERSHIP_MANAGER_ROLE_ID")
        if not channel_id or not role_id:
            return
        try:
            expected_channel = int(channel_id)
            manager_role_id = int(role_id)
        except ValueError:
            return
        if message.channel.id != expected_channel:
            return

        member = message.author
        if not isinstance(member, discord.Member) or not any(
            role.id == manager_role_id for role in member.roles
        ):
            return

        links = set(INVITE_RE.findall(message.content or ""))
        if not links:
            return

        collection = get_db()["partnership_posts"]
        for link in links:
            await collection.update_one(
                {"guild_id": str(message.guild.id), "message_id": str(message.id), "invite_url": link},
                {"$setOnInsert": {
                    "guild_id": str(message.guild.id),
                    "channel_id": str(message.channel.id),
                    "message_id": str(message.id),
                    "manager_id": str(member.id),
                    "invite_url": link,
                    "created_at": datetime.now(timezone.utc),
                }},
                upsert=True,
            )


async def setup(bot):
    await bot.add_cog(Partnership(bot))
