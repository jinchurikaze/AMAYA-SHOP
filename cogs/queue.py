import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from models import order as order_model

log = logging.getLogger("amaya.queue")


def reactions_from_env() -> list[str]:
    """Load all configured order reaction emojis."""
    raw = os.getenv("ORDER_REACTIONS", "")
    return [emoji for emoji in raw.replace(",", " ").split() if emoji]


class Queue(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="queue",
        description="Add an item to the order queue",
    )
    @app_commands.describe(
        item="Item ordered",
        quantity="Quantity of the item",
        payment="Payment method",
        price="Total price paid in pesos",
        deliver_to="Who will receive the order (defaults to you)",
    )
    @app_commands.choices(
        payment=[
            app_commands.Choice(name="gcash", value="gcash"),
            app_commands.Choice(name="maya", value="maya"),
            app_commands.Choice(name="maribank", value="maribank"),
            app_commands.Choice(name="bank transfer", value="bank transfer"),
            app_commands.Choice(name="paypal", value="paypal"),
        ]
    )
    @app_commands.guild_only()
    async def queue(
        self,
        interaction: discord.Interaction,
        item: str,
        quantity: app_commands.Range[int, 1],
        payment: app_commands.Choice[str],
        price: app_commands.Range[int, 0],
        deliver_to: discord.Member = None,
    ):
        channel_id = os.getenv("ORDERLIST_CHANNEL_ID")
        if not channel_id:
            return await interaction.response.send_message(
                "❌ Order list channel isn't configured (`ORDERLIST_CHANNEL_ID`).",
                ephemeral=True,
            )

        try:
            order_list = interaction.guild.get_channel(int(channel_id))
        except (ValueError, TypeError):
            order_list = None

        if not isinstance(order_list, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message(
                "❌ The configured order list channel wasn't found. "
                "Check `ORDERLIST_CHANNEL_ID`.",
                ephemeral=True,
            )

        command_channel = interaction.channel
        if not isinstance(command_channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message(
                "❌ This command must be used in a text channel or thread.",
                ephemeral=True,
            )

        # Acknowledge privately while the database and channel messages are handled.
        await interaction.response.defer(ephemeral=True)
        customer = deliver_to or interaction.user
        payment_method = payment.value.lower()

        try:
            order = await order_model.create_order(
                user_id=customer.id,
                username=customer.name,
                item=item,
                quantity=quantity,
                price=price,
                payment=payment_method,
            )

            command_channel_url = (
                f"https://discord.com/channels/"
                f"{interaction.guild.id}/{interaction.channel_id}"
            )
            message = (
                "\u2800\n"
                "         **order confirmation** "
                "<:040:1498665961354694767>\n"
                f"  •    **[queued]({command_channel_url}) ；"
                f"{quantity}．{item}**\n"
                f"  •    paid by―  {payment_method}，₱{price}\n"
                f"  •    deliver to〝{customer.mention}\n"
                "\u2800"
            )

            # Post the order confirmation only in the configured order channel.
            sent = await order_list.send(
                content=message,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await order_model.set_message_id(order["_id"], sent.id)

            for emoji in reactions_from_env():
                try:
                    await sent.add_reaction(discord.PartialEmoji.from_str(emoji))
                except (discord.HTTPException, ValueError) as err:
                    log.warning("Couldn't add reaction %r: %s", emoji, err)

            # This normal channel message remains visible in channel history.
            view = discord.ui.View()
            view.add_item(
                discord.ui.Button(
                    label="View Order List",
                    style=discord.ButtonStyle.link,
                    url=(
                        f"https://discord.com/channels/"
                        f"{interaction.guild.id}/{order_list.id}"
                    ),
                )
            )
            await command_channel.send(
                "♡ order confirmation added to the queue!",
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        except Exception:
            log.exception("Failed to create queue order")
            await interaction.edit_original_response(
                content=(
                    "❌ Something went wrong while creating the order. "
                    "Please check the bot logs."
                )
            )


async def setup(bot):
    await bot.add_cog(Queue(bot))
