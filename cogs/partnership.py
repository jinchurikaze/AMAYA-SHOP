import logging
import os
import re
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db


log = logging.getLogger("amaya.partnership")
INVITE_RE = re.compile(
    r"https?://(?:www\.)?(?:discord\.gg/|discord(?:app)?\.com/invite/)([A-Za-z0-9-]+)",
    re.IGNORECASE,
)


def invite_codes(text: str) -> list[str]:
    """Return distinct Discord invite codes in their original case."""
    return list(dict.fromkeys(INVITE_RE.findall(text or "")))


def invite_code_from_url(value: str) -> str | None:
    match = INVITE_RE.search(value or "")
    return match.group(1) if match else None


def message_link_text(message: discord.Message) -> str:
    """Include invite URLs Discord placed in an embed as well as message text."""
    parts = [message.content or ""]
    for embed in message.embeds:
        parts.extend([embed.title or "", embed.description or "", embed.url or ""])
        parts.extend(f"{field.name} {field.value}" for field in embed.fields)
    return "\n".join(parts)


def entry_server_key(entry: dict) -> str | None:
    """Normalize current and older stored posts for unique-server counts."""
    return entry.get("invite_code") or invite_code_from_url(entry.get("invite_url", ""))


def representative_ids(message: discord.Message) -> list[str]:
    """Return 1–3 distinct, non-bot member mentions from a partnership post."""
    members = {
        mentioned.id: mentioned
        for mentioned in message.mentions
        if isinstance(mentioned, discord.Member)
        and message.guild is not None
        and mentioned.guild.id == message.guild.id
        and not mentioned.bot
    }
    if not 1 <= len(members) <= 3:
        return []
    return [str(member_id) for member_id in members]


def valid_representatives(entry: dict) -> list[str]:
    reps = entry.get("member_ids", [])
    if not isinstance(reps, list):
        return []
    unique_reps = list(dict.fromkeys(str(rep) for rep in reps))
    return unique_reps if 1 <= len(unique_reps) <= 3 else []


async def record_partnership_message(message: discord.Message, manager_role_id: int) -> int:
    """Store each valid invite once for its manager; return the number newly stored."""
    if message.guild is None or message.author.bot:
        return 0
    manager = message.author
    if not isinstance(manager, discord.Member) or not any(
        role.id == manager_role_id for role in manager.roles
    ):
        return 0

    codes = invite_codes(message_link_text(message))
    reps = representative_ids(message)
    if not codes or not reps:
        return 0

    collection = get_db()["partnership_posts"]
    added = 0
    for code in codes:
        record_key = {
            "guild_id": str(message.guild.id),
            "manager_id": str(manager.id),
            "invite_code": code,
        }
        result = await collection.update_one(
            record_key,
            {"$setOnInsert": {
                **record_key,
                "channel_id": str(message.channel.id),
                "message_id": str(message.id),
                "member_ids": reps,
                "invite_url": f"https://discord.gg/{code}",
                "created_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
        if result.upserted_id is not None:
            added += 1
    return added


class Partnership(commands.GroupCog, name="partnership", description="Track partnership posts"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    async def _get_representatives(self, guild: discord.Guild, entry: dict) -> list[str]:
        """Use stored reps or validate and backfill a legacy tracked Discord post."""
        reps = valid_representatives(entry)
        if reps:
            return reps

        code = entry_server_key(entry)
        try:
            channel_id = int(entry["channel_id"])
            message_id = int(entry["message_id"])
            manager_id = int(entry["manager_id"])
            channel = guild.get_channel(channel_id) or self.bot.get_channel(channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(channel_id)
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                return []
            if channel.guild.id != guild.id:
                return []
            post = await channel.fetch_message(message_id)
        except (KeyError, ValueError, TypeError):
            return []
        except discord.HTTPException as err:
            log.info("Could not fetch legacy partnership post: %s", err)
            return []

        if post.author.id != manager_id or not code:
            return []
        if code not in invite_codes(message_link_text(post)):
            return []

        reps = representative_ids(post)
        if reps:
            await get_db()["partnership_posts"].update_one(
                {"_id": entry["_id"]},
                {"$set": {"invite_code": code, "member_ids": reps}},
            )
        return reps

    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="list", description="Show recently tracked partnership servers")
    @app_commands.describe(limit="Number of recent servers to show")
    async def list_(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 10] = 10,
    ):
        await interaction.response.send_message(
            "Checking saved partnership posts…", ephemeral=True
        )
        cursor = get_db()["partnership_posts"].find(
            {"guild_id": str(interaction.guild_id)}
        ).sort("created_at", -1)
        entries = []
        seen = set()
        async for entry in cursor:
            reps = await self._get_representatives(interaction.guild, entry)
            if not reps:
                continue
            server_key = entry_server_key(entry)
            key = (entry.get("manager_id"), server_key or entry.get("message_id"))
            if key in seen:
                continue
            seen.add(key)
            entries.append((entry, reps))
            if len(entries) >= limit:
                break

        if not entries:
            return await interaction.edit_original_response(
                content="No valid partnership posts have been tracked yet. "
                "Older posts can only be checked if I can read their channel history."
            )

        lines = []
        for entry, reps in entries:
            timestamp = entry.get("created_at")
            stamp = discord.utils.format_dt(timestamp, style="R") if timestamp else "unknown time"
            post_url = (
                f"https://discord.com/channels/{entry.get('guild_id')}/"
                f"{entry.get('channel_id')}/{entry.get('message_id')}"
            )
            rep_text = ", ".join(f"<@{member_id}>" for member_id in reps)
            lines.append(
                f"• {entry.get('invite_url', 'link unavailable')} — "
                f"manager <@{entry.get('manager_id')}> · reps: {rep_text} · "
                f"{stamp} · [post]({post_url})"
            )
        await interaction.edit_original_response(
            content="\n".join(lines),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.guild_only()
    @app_commands.command(name="stats", description="Count unique partner servers for a manager")
    @app_commands.describe(member="Manager to check; defaults to you")
    async def stats(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ):
        if (
            member is not None
            and member.id != interaction.user.id
            and not interaction.user.guild_permissions.manage_guild
        ):
            return await interaction.response.send_message(
                "You can check your own total. Manage Server permission is required "
                "to check another member.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            "Checking saved partnership posts…", ephemeral=True
        )
        manager = member or interaction.user
        cursor = get_db()["partnership_posts"].find({
            "guild_id": str(interaction.guild_id),
            "manager_id": str(manager.id),
        })
        servers = set()
        async for entry in cursor:
            code = entry_server_key(entry)
            reps = await self._get_representatives(interaction.guild, entry)
            if code and reps:
                servers.add(code)
        await interaction.edit_original_response(
            content=(
                f"🤝 **{discord.utils.escape_markdown(manager.display_name)}** has partnered "
                f"with **{len(servers)} unique server(s)**."
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="sync", description="Import valid partnerships from channel history")
    @app_commands.describe(limit="Recent messages to scan (maximum 5000)")
    async def sync(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 5000] = 1000,
    ):
        channel_id = os.getenv("PARTNERSHIP_CHANNEL_ID")
        role_id = os.getenv("PARTNERSHIP_MANAGER_ROLE_ID")
        try:
            target_channel_id = int(channel_id or "")
            manager_role_id = int(role_id or "")
        except ValueError:
            return await interaction.response.send_message(
                "Set valid `PARTNERSHIP_CHANNEL_ID` and `PARTNERSHIP_MANAGER_ROLE_ID` "
                "values in `.env` first.",
                ephemeral=True,
            )

        channel = interaction.guild.get_channel(target_channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message(
                "The configured partnership channel was not found in this server.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            f"Scanning up to {limit} recent messages in {channel.mention}…",
            ephemeral=True,
        )
        scanned = added = 0
        try:
            async for message in channel.history(limit=limit):
                scanned += 1
                added += await record_partnership_message(message, manager_role_id)
        except discord.Forbidden:
            return await interaction.edit_original_response(
                content="I need **View Channel** and **Read Message History** permissions "
                "in the partnership channel to scan older posts."
            )
        except discord.HTTPException as err:
            log.exception("Partnership history scan failed")
            return await interaction.edit_original_response(
                content=f"The history scan stopped after {scanned} messages: {err}"
            )

        await interaction.edit_original_response(
            content=(
                f"✅ Scanned {scanned} messages and added {added} new qualifying "
                "partnership server(s). Repeated invite links were skipped."
            )
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:
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

        await record_partnership_message(message, manager_role_id)


async def setup(bot):
    await bot.add_cog(Partnership(bot))
