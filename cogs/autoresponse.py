import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db


log = logging.getLogger("amaya.autoresponse")
DELETE_MARKER_RE = re.compile(r"(?<!\S)\{delete\}(?!\S)", re.IGNORECASE)


def parse_trigger(value: str) -> tuple[str, bool]:
    """Remove the optional {delete} marker and return the trigger and delete flag."""
    delete_trigger = bool(DELETE_MARKER_RE.search(value))
    trigger = DELETE_MARKER_RE.sub(" ", value)
    return " ".join(trigger.split()), delete_trigger


@app_commands.default_permissions(manage_messages=True)
@app_commands.guild_only()
class AutoResponse(commands.GroupCog, name="autoresponse", description="Manage automatic responses"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="add", description="Add or replace an automatic response")
    @app_commands.describe(
        trigger="Text that activates the response; add {delete} to delete the trigger message",
        response="Response to send as a separate message",
    )
    async def add(self, interaction: discord.Interaction, trigger: str, response: str):
        trigger, delete_trigger = parse_trigger(trigger.strip())
        response = response.strip()
        if not trigger or len(trigger) > 80:
            return await interaction.response.send_message(
                "Trigger must be between 1 and 80 characters, excluding {delete}.", ephemeral=True
            )
        if not response or len(response) > 1800:
            return await interaction.response.send_message(
                "Response must be between 1 and 1800 characters.", ephemeral=True
            )

        await get_db()["auto_responses"].update_one(
            {"guild_id": str(interaction.guild_id), "trigger_key": trigger.casefold()},
            {"$set": {
                "guild_id": str(interaction.guild_id),
                "trigger": trigger,
                "trigger_key": trigger.casefold(),
                "response": response,
                "delete_trigger": delete_trigger,
                "updated_by": str(interaction.user.id),
            }},
            upsert=True,
        )
        delete_note = " (trigger message will be deleted)" if delete_trigger else ""
        await interaction.response.send_message(
            f"✅ Auto-response saved for **{trigger}**{delete_note}.", ephemeral=True
        )

    @app_commands.command(name="remove", description="Remove an automatic response")
    @app_commands.describe(trigger="The trigger to remove; {delete} is optional")
    async def remove(self, interaction: discord.Interaction, trigger: str):
        trigger, _ = parse_trigger(trigger.strip())
        result = await get_db()["auto_responses"].delete_one({
            "guild_id": str(interaction.guild_id),
            "trigger_key": trigger.casefold(),
        })
        message = "✅ Auto-response removed." if result.deleted_count else "No matching trigger was found."
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="list", description="List this server's automatic responses")
    async def list_(self, interaction: discord.Interaction):
        entries = await get_db()["auto_responses"].find(
            {"guild_id": str(interaction.guild_id)}
        ).sort("trigger_key", 1).to_list(length=10)
        if not entries:
            return await interaction.response.send_message(
                "No auto-responses are configured.", ephemeral=True
            )
        lines = [
            f"• **{entry['trigger']}{' {delete}' if entry.get('delete_trigger') else ''}** → {entry['response'][:100]}"
            for entry in entries
        ]
        if len(entries) == 10:
            lines.append("Showing the first 10 triggers.")
        await interaction.response.send_message(
            "\n".join(lines), ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or not message.content:
            return

        entries = await get_db()["auto_responses"].find(
            {"guild_id": str(message.guild.id)}
        ).to_list(length=100)
        content = message.content.casefold()
        matches = [
            entry for entry in entries
            if entry.get("trigger_key") and entry["trigger_key"] in content
        ]
        if not matches:
            return

        # Use the longest matching trigger to avoid a shorter trigger winning by accident.
        match = max(matches, key=lambda entry: len(entry["trigger_key"]))
        # Send a standalone channel message rather than replying to the trigger message.
        await message.channel.send(
            match["response"],
            allowed_mentions=discord.AllowedMentions.none(),
        )

        if match.get("delete_trigger"):
            try:
                await message.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                log.warning(
                    "Cannot delete auto-response trigger message in channel %s; "
                    "the bot needs Manage Messages permission.",
                    message.channel.id,
                )
            except discord.HTTPException:
                log.exception(
                    "Failed to delete auto-response trigger message %s", message.id
                )


async def setup(bot):
    await bot.add_cog(AutoResponse(bot))
