import discord
from discord import app_commands
from discord.ext import commands


class EmbedCmd(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="embed", description="Send an order confirmation embed")
    async def embed(self, interaction: discord.Interaction):
        order = {
            "username": interaction.user.name,
            "quantity": 1,
            "item": "Sample Item",
            "price": 100,
            "payment": "GCash",
            "status": "done",
            "_id": "12345",
        }

        status_emoji = "🟢" if order["status"] == "done" else "🟠"

        embed = discord.Embed(
            color=0x2B2D31,
            description="\n".join(
                [
                    f"### {order['username']}",
                    "",
                    f"> 📦 item : **{order['item']}**",
                    f"> 🔢 quantity : **{order['quantity']}**",
                    f"> 💸 price : **₱{order['price']}**",
                    f"> 💳 payment : **{order['payment']}**",
                    "",
                    f"> {status_emoji} status : **{order['status']}**",
                ]
            ),
        )
        embed.set_author(name="order confirmed", icon_url="https://i.imgur.com/7bIYpKp.png")
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"Order ID • {order['_id']}")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(EmbedCmd(bot))
