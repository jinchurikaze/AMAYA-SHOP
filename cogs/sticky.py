import discord
from discord import app_commands
from discord.ext import commands

from sticky_data import load_sticky_data, save_sticky_data


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
class Sticky(
    commands.GroupCog,
    name="sticky",
    description="Manage sticky messages in this channel",
):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="set", description="Set a sticky message for this channel")
    @app_commands.describe(
        message="The sticky message content",
        button_label="Optional text for the channel button",
        button_channel="Optional channel the button opens",
    )
    async def set_(
        self,
        interaction: discord.Interaction,
        message: str,
        button_label: str = None,
        button_channel: discord.TextChannel = None,
    ):
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message(
                "This command can only be used in a text channel or thread.",
                ephemeral=True,
            )

        if bool(button_label) != bool(button_channel):
            return await interaction.response.send_message(
                "To add a button, provide both its label and destination channel.",
                ephemeral=True,
            )

        data = load_sticky_data()
        current = data.get(str(channel.id))

        await delete_old_sticky(channel, current and current.get("messageId"))

        view = None
        if button_label and button_channel:
            view = discord.ui.View()
            view.add_item(
                discord.ui.Button(
                    label=button_label[:80],
                    style=discord.ButtonStyle.link,
                    url=button_channel.jump_url,
                )
            )

        sent = await channel.send(
            message,
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )

        data[str(channel.id)] = {
            "content": message,
            "messageId": str(sent.id),
            "buttonLabel": button_label,
            "buttonChannelId": str(button_channel.id) if button_channel else None,
        }
        save_sticky_data(data)

        await interaction.response.send_message(
            "Sticky message set for this channel.",
            ephemeral=True,
        )

    @app_commands.command(
        name="view",
        description="View the current sticky message in this channel",
    )
    async def view(self, interaction: discord.Interaction):
        current = load_sticky_data().get(str(interaction.channel.id))
        if not current:
            return await interaction.response.send_message(
                "There is no sticky message set in this channel.",
                ephemeral=True,
            )

        text = f"📌 Current sticky message:\n{current['content']}"
        if current.get("buttonLabel") and current.get("buttonChannelId"):
            text += (
                f"\nButton: {current['buttonLabel']} "
                f"(channel ID: {current['buttonChannelId']})"
            )

        await interaction.response.send_message(
            text,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(
        name="remove",
        description="Remove the sticky message from this channel",
    )
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