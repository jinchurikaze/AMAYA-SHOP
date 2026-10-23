import logging
import re

import discord
from discord import app_commands
from discord.ext import commands


log = logging.getLogger("amaya.ticket")
TICKET_NUMBER_RE = re.compile(r"[.．](\d+)$")


def renamed_ticket_channel(current_name: str, requested_name: str) -> str | None:
    """Normalize a requested label and keep the existing ticket number suffix."""
    number_match = TICKET_NUMBER_RE.search(current_name)
    requested = requested_name.strip()
    requested_suffix = TICKET_NUMBER_RE.search(requested)
    if requested_suffix:
        requested = requested[:requested_suffix.start()]

    base = re.sub(r"[^a-z0-9-]+", "-", requested.casefold()).strip("-")
    base = re.sub(r"-{2,}", "-", base).strip("-")
    if not base:
        return None

    if number_match:
        return f"{base}．{number_match.group(1)}"[:100]
    return base[:100]


class Ticket(commands.GroupCog, name="ticket", description="Manage ticket channels"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.guild_only()
    @app_commands.command(name="rename", description="Rename the current ticket channel")
    @app_commands.describe(name="New ticket name; the ticket number is kept automatically")
    async def rename(self, interaction: discord.Interaction, name: str):
        # Acknowledge first so permission checks and Discord's channel edit cannot
        # leave the command showing “The application did not respond”.
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send(
                "Use this command inside a ticket text channel.", ephemeral=True
            )

        member = interaction.user
        if (
            not isinstance(member, discord.Member)
            or not channel.permissions_for(member).manage_channels
        ):
            return await interaction.followup.send(
                "You need Manage Channels permission to rename this ticket.",
                ephemeral=True,
            )

        ticket_number = TICKET_NUMBER_RE.search(channel.name)
        category_name = channel.category.name.casefold() if channel.category else ""
        is_ticket = (
            "ticket" in channel.name.casefold()
            or "ticket" in category_name
            or ticket_number is not None
        )
        if not is_ticket:
            return await interaction.followup.send(
                "This channel doesn't look like a ticket. Ticket names ending in "
                "a number, such as order．1194, are supported.",
                ephemeral=True,
            )

        clean_name = renamed_ticket_channel(channel.name, name)
        if not clean_name:
            return await interaction.followup.send(
                "Enter a ticket name containing letters or numbers.",
                ephemeral=True,
            )

        try:
            await channel.edit(name=clean_name, reason=f"Ticket renamed by {member}")
        except discord.Forbidden:
            return await interaction.followup.send(
                "The bot needs Manage Channels permission to rename this ticket.",
                ephemeral=True,
            )
        except discord.HTTPException:
            log.exception("Discord rejected ticket rename for channel %s", channel.id)
            return await interaction.followup.send(
                "Discord couldn't rename this ticket. Please try again.",
                ephemeral=True,
            )
        except Exception:
            log.exception("Unexpected ticket rename failure for channel %s", channel.id)
            return await interaction.followup.send(
                "Something went wrong while renaming the ticket.", ephemeral=True
            )

        await interaction.followup.send(
            f"✅ Ticket renamed to **{clean_name}**.", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Ticket(bot))
