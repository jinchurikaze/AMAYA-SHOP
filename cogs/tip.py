import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from utils import js_num

log = logging.getLogger("amaya.tip")


class Tip(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tip", description="Log a tip to the tip jar")
    @app_commands.rename(from_="from")
    @app_commands.describe(
        from_="Who tipped",
        amount="Tip amount",
    )
    @app_commands.default_permissions(manage_messages=True)
    async def tip(
        self,
        interaction: discord.Interaction,
        from_: discord.User,
        amount: app_commands.Range[float, 0.01],
    ):
        tip_jar_id = os.getenv("TIP_JAR_CHANNEL_ID")
        if not tip_jar_id:
            return await interaction.response.send_message(
                "❌ Tip jar channel isn't configured.",
                ephemeral=True,
            )

        try:
            tip_jar = await interaction.client.fetch_channel(int(tip_jar_id))
            if not isinstance(tip_jar, (discord.TextChannel, discord.Thread)):
                raise TypeError("Configured tip jar is not a text channel.")

            message = (
                f"thank u for the ₱{js_num(amount)} tip! "
                f"{from_.mention} <:007:1498664891014316032>"
            )
            await tip_jar.send(
                message,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except Exception:
            log.exception("Tip jar send failed")
            return await interaction.response.send_message(
                "❌ Couldn't post to the tip jar. Check the bot's permissions there.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            "tip logged to the tip jar!",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Tip(bot))