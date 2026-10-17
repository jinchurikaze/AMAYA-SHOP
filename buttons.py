import logging

import discord

from models import order as order_model

log = logging.getLogger("amaya.buttons")


class OrderButtons(discord.ui.View):
    """Persistent grey Processing and Delivered buttons."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _update_status(
        self,
        interaction: discord.Interaction,
        status: str,
        color: int,
    ):
        try:
            # Only staff with Manage Messages can update orders.
            if not interaction.user.guild_permissions.manage_messages:
                return await interaction.response.send_message(
                    "❌ You don't have permission to update orders.",
                    ephemeral=True,
                )

            if not interaction.message or not interaction.message.embeds:
                return await interaction.response.send_message(
                    "❌ Couldn't find the order embed.",
                    ephemeral=True,
                )

            # Save the new status in the existing database.
            await order_model.set_status_by_message(
                interaction.message.id,
                status,
            )

            # Update the existing confirmation embed.
            embed = interaction.message.embeds[0].copy()
            embed.color = color
            embed.set_footer(text=f"Order status: {status}")

            # Keep both grey buttons available.
            await interaction.response.edit_message(
                embed=embed,
                view=self,
            )

            # Preserve the existing sticky-message refresh.
            refresh = getattr(
                interaction.client,
                "schedule_sticky_refresh",
                None,
            )

            if refresh:
                result = refresh(interaction.channel)
                if hasattr(result, "__await__"):
                    await result

        except Exception:
            log.exception("Order button error")

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Couldn't update that order.",
                    ephemeral=True,
                )

    @discord.ui.button(
        label="Processing",
        style=discord.ButtonStyle.secondary,
        emoji="📦",
        custom_id="order_processing",
    )
    async def processing(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await self._update_status(
            interaction,
            "processing",
            0xFEE75C,
        )

    @discord.ui.button(
        label="Delivered",
        style=discord.ButtonStyle.secondary,
        emoji="💗",
        custom_id="order_delivered",
    )
    async def delivered(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await self._update_status(
            interaction,
            "delivered",
            0x57F287,
        )