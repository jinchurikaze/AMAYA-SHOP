import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import can_moderate

log = logging.getLogger("amaya.kick")


class Kick(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="kick", description="Kick a user from the server")
    @app_commands.describe(user="The user to kick", reason="Reason for kicking")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: Optional[str] = None,
    ):
        reason = reason or "No Reason Provided"

        member = interaction.guild.get_member(user.id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(user.id)
            except discord.NotFound:
                member = None

        if member is None:
            return await interaction.response.send_message(
                "That user is not in the server!", ephemeral=True
            )

        if not can_moderate(interaction.guild, member, "kick_members"):
            return await interaction.response.send_message(
                "I cannot kick this user. They may have higher permission than me",
                ephemeral=True,
            )

        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(
                f"Successfully kicked **{user}** from the server.\nReason: {reason}"
            )
        except Exception:
            log.exception("kick failed")
            await interaction.response.send_message(
                "There was an error trying to kick this user!", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Kick(bot))
