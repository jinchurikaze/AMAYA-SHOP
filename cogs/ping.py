import discord
from discord import app_commands
from discord.ext import commands


class Ping(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Replies with Pong and latency information!")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pinging...")
        sent = await interaction.original_response()
        pingtime = round((sent.created_at - interaction.created_at).total_seconds() * 1000)
        api = round(self.bot.latency * 1000)
        await interaction.edit_original_response(
            content=f"Pong! Latency is {pingtime}ms.\nAPI Latency is {api}ms."
        )


async def setup(bot):
    await bot.add_cog(Ping(bot))
