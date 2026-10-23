import re

import discord
from discord import app_commands
from discord.ext import commands


class Ticket(commands.GroupCog, name="ticket", description="Manage ticket channels"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.guild_only()
    @app_commands.command(name="rename", description="Rename the current ticket channel")
    @app_commands.describe(name="New ticket name")
    async def rename(self, interaction: discord.Interaction, name: str):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "Use this command inside a ticket text channel.", ephemeral=True
            )

        member = interaction.user
        if not isinstance(member, discord.Member) or not channel.permissions_for(member).manage_channels:
            return await interaction.response.send_message(
                "You need Manage Channels permission to rename this ticket.", ephemeral=True
            )

        category_name = channel.category.name.casefold() if channel.category else ""
        if "ticket" not in channel.name.casefold() and "ticket" not in category_name:
            return await interaction.response.send_message(
                "This channel doesn't appear to be a ticket channel.", ephemeral=True
            )

        clean_name = re.sub(r"[^a-z0-9-]+", "-", name.casefold()).strip("-")
        clean_name = re.sub(r"-{2,}", "-", clean_name)[:100].strip("-")
        if not clean_name:
            return await interaction.response.send_message(
                "Enter a name containing letters or numbers.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        try:
            await channel.edit(name=clean_name, reason=f"Ticket renamed by {member}")
        except discord.Forbidden:
            return await interaction.followup.send(
                "The bot needs Manage Channels permission to rename this ticket.", ephemeral=True
            )
        except discord.HTTPException:
            return await interaction.followup.send(
                "Discord couldn't rename this ticket. Please try again.", ephemeral=True
            )
        await interaction.followup.send(
            f"✅ Ticket renamed to **{clean_name}**.", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Ticket(bot))
