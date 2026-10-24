import logging
import re

import discord
from discord import app_commands
from discord.ext import commands


log = logging.getLogger("amaya.ticket")
TICKET_SUFFIX_RE = re.compile(r"[.．]([^.]*)$")


def _clean_channel_part(value: str) -> str:
    value = re.sub(r"[^a-z0-9-]+", "-", value.casefold()).strip("-")
    return re.sub(r"-{2,}", "-", value)


def renamed_ticket_channel(before_dot: str, after_dot: str | None = None) -> str | None:
    """Build a ticket name as either one label or two dot-separated labels."""
    before_dot = before_dot.strip()
    after_dot = after_dot.strip() if after_dot else ""

    # Keep the two-field format (for example, 1000．vp), while also allowing
    # a complete dotted name to be pasted into the first field.
    if not after_dot:
        separator = re.search(r"[.．]", before_dot)
        if separator:
            before_dot, after_dot = before_dot[:separator.start()], before_dot[separator.end():]

    before = _clean_channel_part(before_dot)
    if not after_dot:
        return before[:100] or None

    after = _clean_channel_part(after_dot)
    if not before or not after:
        return None

    # Discord channel names have a 100-character maximum.
    available = 99  # one character is reserved for the fullwidth dot
    if len(before) + len(after) > available:
        before = before[: max(1, available - len(after))]
        after = after[: available - len(before)]
    return f"{before}．{after}"

class Ticket(commands.GroupCog, name="ticket", description="Manage ticket channels"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.guild_only()
    @app_commands.command(name="rename", description="Rename the current ticket channel")
    @app_commands.describe(
        before_dot="Ticket name, or text before the dot (for example, done or 1000)",
        after_dot="Optional text after the dot (for example, vp)",
    )
    async def rename(
        self,
        interaction: discord.Interaction,
        before_dot: str,
        after_dot: str | None = None,
    ):
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

        ticket_suffix = TICKET_SUFFIX_RE.search(channel.name)
        category_name = channel.category.name.casefold() if channel.category else ""
        is_ticket = (
            "ticket" in channel.name.casefold()
            or "ticket" in category_name
            or ticket_suffix is not None
        )
        if not is_ticket:
            return await interaction.followup.send(
                "This channel doesn't look like a ticket. Ticket names ending in "
                "a dot-separated name, such as order．1194, are supported.",
                ephemeral=True,
            )

        clean_name = renamed_ticket_channel(before_dot, after_dot)
        if not clean_name:
            return await interaction.followup.send(
                "Enter a ticket name, or provide text on both sides of the dot.",
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
            f" Ticket renamed to **{clean_name}**.", ephemeral=True
        )


    @app_commands.guild_only()
    @app_commands.command(name="move", description="Move this ticket to another category")
    @app_commands.describe(
        category="The category to move this ticket into",
        sync_permissions="Use the destination category's permissions instead of preserving current access",
    )
    async def move(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        sync_permissions: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        guild = interaction.guild
        if not isinstance(channel, discord.TextChannel) or guild is None:
            return await interaction.followup.send(
                "Use this command inside a ticket text channel.", ephemeral=True
            )

        if category.guild.id != guild.id:
            return await interaction.followup.send(
                "Choose a category from this server.", ephemeral=True
            )

        member = interaction.user
        if (
            not isinstance(member, discord.Member)
            or not channel.permissions_for(member).manage_channels
        ):
            return await interaction.followup.send(
                "You need Manage Channels permission to move this ticket.",
                ephemeral=True,
            )

        ticket_suffix = TICKET_SUFFIX_RE.search(channel.name)
        category_name = channel.category.name.casefold() if channel.category else ""
        is_ticket = (
            "ticket" in channel.name.casefold()
            or "ticket" in category_name
            or ticket_suffix is not None
        )
        if not is_ticket:
            return await interaction.followup.send(
                "This channel doesn't look like a ticket.", ephemeral=True
            )

        bot_member = guild.me
        if bot_member is None or not channel.permissions_for(bot_member).manage_channels:
            return await interaction.followup.send(
                "The bot needs Manage Channels permission to move this ticket.",
                ephemeral=True,
            )

        try:
            await channel.edit(
                category=category,
                sync_permissions=sync_permissions,
                reason=f"Ticket moved by {member}",
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                "The bot needs Manage Channels permission to move this ticket.",
                ephemeral=True,
            )
        except discord.HTTPException:
            log.exception("Discord rejected ticket move for channel %s", channel.id)
            return await interaction.followup.send(
                "Discord couldn't move this ticket. Please try again.",
                ephemeral=True,
            )

        permission_note = (
            " Destination category permissions applied."
            if sync_permissions
            else " Existing ticket access permissions were preserved."
        )
        await interaction.followup.send(
            f"Ticket moved to **{category.name}**.{permission_note}",
            ephemeral=True,
        )

async def setup(bot):
    await bot.add_cog(Ticket(bot))

