import discord
from discord import app_commands
from discord.ext import commands


class Send(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="send", description="Sends a custom message")
    @app_commands.describe(message="The message to send")
    async def send(self, interaction: discord.Interaction, message: str):
        # Reply first (ephemeral so only the user sees it)
        await interaction.response.send_message("✅ Message sent!", ephemeral=True)
        # Then send the actual message to the channel
        await interaction.channel.send(message)


async def setup(bot):
    await bot.add_cog(Send(bot))
