import discord
from discord import app_commands
from discord.ext import commands

from sticky_data import load_sticky_data, save_sticky_data


def make_view(buttons):
    if not buttons:
        return None

    view = discord.ui.View(timeout=None)

    for button in buttons[:2]:
        view.add_item(
            discord.ui.Button(
                label=button["label"],
                style=discord.ButtonStyle.link,
                url=button["url"],
            )
        )

    return view


async def delete_old_sticky(channel, message_id):
    if channel is None or not message_id:
        return

    try:
        old = await channel.fetch_message(int(message_id))
        await old.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
        pass


@app_commands.default_permissions(manage_messages=True)
@app_commands.guild_only()
class Sticky(commands.GroupCog, name="sticky", description="Manage sticky messages"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="set", description="Set a sticky message in this channel")
    @app_commands.describe(
        message="The sticky message content",
        button_1_label="Optional label for the first button",
        button_1_channel="Channel the first button opens",
        button_2_label="Optional label for the second button",
        button_2_channel="Channel the second button opens",
    )
    async def set_(
        self,
        interaction: discord.Interaction,
        message: str,
        button_1_label: str = None,
        button_1_channel: discord.TextChannel = None,
        button_2_label: str = None,
        button_2_channel: discord.TextChannel = None,
    ):
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message(
                "This command can only be used in a text channel or thread.",
                ephemeral=True,
            )

        pairs = [
            (button_1_label, button_1_channel),
            (button_2_label, button_2_channel),
        ]

        for label, destination in pairs:
            if bool(label) != bool(destination):
                return await interaction.response.send_message(
                    "For each button, provide both its label and destination channel.",
                    ephemeral=True,
                )

        buttons = []
        for label, destination in pairs:
            if label and destination:
                buttons.append({
                    "label": label[:80],
                    "url": (
                        f"https://discord.com/channels/"
                        f"{interaction.guild.id}/{destination.id}"
                    ),
                })

        data = load_sticky_data()
        current = data.get(str(channel.id))
        await delete_old_sticky(
            channel,
            current and current.get("messageId"),
        )

        sent = await channel.send(
            message,
            view=make_view(buttons),
            allowed_mentions=discord.AllowedMentions.none(),
        )

        data[str(channel.id)] = {
            "content": message,
            "messageId": str(sent.id),
            "buttons": buttons,
        }
        save_sticky_data(data)

        await interaction.response.send_message(
            "Sticky message set for this channel.",
            ephemeral=True,
        )

    @app_commands.command(name="view", description="View this channel's sticky message")
    async def view(self, interaction: discord.Interaction):
        current = load_sticky_data().get(str(interaction.channel.id))
        if not current:
            return await interaction.response.send_message(
                "There is no sticky message set in this channel.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            f"📌 Current sticky message:\n{current['content']}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="remove", description="Remove this channel's sticky message")
    async def remove(self, interaction: discord.Interaction):
        channel = interaction.channel
        data = load_sticky_data()
        current = data.get(str(channel.id))

        if not current:
            return await interaction.response.send_message(
                "There is no sticky message set in this channel.",
                ephemeral=True,
            )

        await delete_old_sticky(channel, current.get("messageId"))
        del data[str(channel.id)]
        save_sticky_data(data)

        await interaction.response.send_message(
            "Sticky message removed from this channel.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Sticky(bot))