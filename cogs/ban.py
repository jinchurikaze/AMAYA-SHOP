import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import can_moderate

log = logging.getLogger("amaya.ban")


class Ban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ban", description="Ban a user from the server")
    @app_commands.describe(target="The user to ban", reason="Reason for banning")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(
        self,
        interaction: discord.Interaction,
        target: discord.User,
        reason: Optional[str] = None,
    ):
        reason = reason or "No reason provided"

        member = interaction.guild.get_member(target.id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(target.id)
            except discord.NotFound:
                member = None

        if member is None:
            return await interaction.response.send_message(
                "That user is not in this server!", ephemeral=True
            )

        if not can_moderate(interaction.guild, member, "ban_members"):
            return await interaction.response.send_message(
                "I cannot ban this user! They may have higher permissions than me.",
                ephemeral=True,
            )

        try:
            await interaction.guild.ban(target, reason=reason)
            await interaction.response.send_message(
                f"Successfully banned **{target}** from the server.\nReason: {reason}"
            )
        except Exception:
            log.exception("ban failed")
            await interaction.response.send_message(
                "There was an error trying to ban this user!", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Ban(bot))
