import logging
import os

import discord

log = logging.getLogger("amaya.monitoring")

FORM_BUTTON_ID = "monitor_form"
MODAL_ID = "monitor_form_modal"


class MonitoringModal(discord.ui.Modal, title="Monitoring Form"):
    email = discord.ui.TextInput(label="item's email/number", max_length=100)
    profile = discord.ui.TextInput(label="profile", max_length=100)
    sharing = discord.ui.TextInput(label="solo or shared", max_length=100)
    device = discord.ui.TextInput(label="device type and brand", max_length=100)
    username = discord.ui.TextInput(label="username", max_length=100)

    def __init__(self):
        super().__init__(custom_id=MODAL_ID)

    async def on_submit(self, interaction: discord.Interaction):
        channel_id = os.getenv("MONITORING_CHANNEL_ID")
        if not channel_id:
            await interaction.response.send_message(
                "❌ Monitoring form isn't set up yet. Please open a ticket."
            )
            return

        embed = discord.Embed(color=0xFFB6C1, title="📋 New Monitoring Form")
        embed.add_field(name="Item's email/number", value=self.email.value, inline=False)
        embed.add_field(name="Profile", value=self.profile.value, inline=True)
        embed.add_field(name="Solo / Shared", value=self.sharing.value, inline=True)
        embed.add_field(name="Device", value=self.device.value, inline=False)
        embed.add_field(name="Username", value=self.username.value, inline=False)
        embed.add_field(
            name="Submitted by",
            value=f"{interaction.user.mention} ({interaction.user})",
            inline=False,
        )
        embed.set_footer(text=f"User ID: {interaction.user.id}")
        embed.timestamp = discord.utils.utcnow()

        try:
            channel = await interaction.client.fetch_channel(int(channel_id))
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except Exception as err:
            log.error("❌ Monitoring form send failed: %s", err)
            await interaction.response.send_message(
                "❌ Couldn't submit your form. Please open a ticket."
            )
            return

        await interaction.response.send_message(
            "✅ Monitoring form submitted! Your warranty is now active. Thank you 💖"
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.error("❌ Monitoring modal error: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ Couldn't submit your form. Please open a ticket."
            )


class MonitorFormButton(discord.ui.Button):
    def __init__(self, emoji: str = "📝"):
        super().__init__(
            label="submit monitoring form",
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=FORM_BUTTON_ID,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(MonitoringModal())


class MonitorFormView(discord.ui.View):
    """Registered once at startup so the button keeps working in old DMs."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MonitorFormButton())
