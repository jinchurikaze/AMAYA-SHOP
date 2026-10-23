import re

import discord
from discord import app_commands
from discord.ext import commands

from sticky_data import load_sticky_data, save_sticky_data


ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")


def make_view(buttons):
    if not buttons:
        return None

    view = discord.ui.View(timeout=None)

    for button in buttons[:2]:
        view.add_item(
            discord.ui.Button(
                label=button.get("label") or "Open link",
                style=discord.ButtonStyle.link,
                url=button["url"],
                emoji=button.get("emoji"),
            )
        )

    return view


def role_ids_in(content):
    return sorted(set(ROLE_MENTION_RE.findall(content or "")))


def make_allowed_mentions(guild, sticky):
    role_ids = sticky.get("allowed_role_ids")
    if role_ids is None:
        role_ids = role_ids_in(sticky.get("content", ""))

    roles = []
    if guild:
        for role_id in role_ids:
            try:
                role = guild.get_role(int(role_id))
            except (TypeError, ValueError):
                role = None
            if role:
                roles.append(role)

    # Only roles explicitly present in the sticky content can ping.
    return discord.AllowedMentions(
        everyone=False,
        users=False,
        roles=roles,
        replied_user=False,
    )


def buttons_from_message(message):
    buttons = []
    for row in message.components:
        for component in getattr(row, "children", []):
            if (
                component.type == discord.ComponentType.button
                and component.style == discord.ButtonStyle.link
                and getattr(component, "url", None)
            ):
                button = {
                    "label": getattr(component, "label", None) or "Open link",
                    "url": component.url,
                }
                emoji = getattr(component, "emoji", None)
                if emoji:
                    button["emoji"] = str(emoji)
                buttons.append(button)
                if len(buttons) == 2:
                    return buttons
    return buttons


async def post_sticky(channel, sticky):
    embeds = [
        discord.Embed.from_dict(raw)
        for raw in sticky.get("embeds", [])[:10]
    ]
    return await channel.send(
        content=sticky.get("content") or None,
        embeds=embeds or None,
        view=make_view(sticky.get("buttons", [])),
        allowed_mentions=make_allowed_mentions(channel.guild, sticky),
    )


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

    @app_commands.command(name="set", description="Set a text sticky message in this channel")
    @app_commands.describe(
        message="The sticky message content (role mentions will ping)",
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
        sticky = {
            "content": message,
            "embeds": [],
            "buttons": buttons,
            "allowed_role_ids": role_ids_in(message),
        }
        sent = await post_sticky(channel, sticky)
        sticky["messageId"] = str(sent.id)
        data[str(channel.id)] = sticky
        save_sticky_data(data)
        await delete_old_sticky(
            channel,
            (data.get(str(channel.id)) or {}).get("messageId")
            if False else None,
        )

        await interaction.response.send_message(
            "Sticky message set for this channel.", ephemeral=True
        )

    @app_commands.command(name="copy", description="Make a message's embed and link buttons sticky")
    @app_commands.describe(message_id="ID of the message to copy from this channel")
    async def copy(self, interaction: discord.Interaction, message_id: str):
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message(
                "This command can only be used in a text channel or thread.",
                ephemeral=True,
            )

        try:
            source = await channel.fetch_message(int(message_id.strip()))
        except ValueError:
            return await interaction.response.send_message(
                "Enter a valid message ID.", ephemeral=True
            )
        except discord.NotFound:
            return await interaction.response.send_message(
                "I couldn't find that message in this channel.", ephemeral=True
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "I need permission to view message history in this channel.",
                ephemeral=True,
            )

        embeds = [embed.to_dict() for embed in source.embeds]
        buttons = buttons_from_message(source)
        content = source.content or ""
        if not content and not embeds:
            return await interaction.response.send_message(
                "That message has no text or embed content to make sticky.",
                ephemeral=True,
            )

        sticky = {
            "content": content,
            "embeds": embeds,
            "buttons": buttons,
            "allowed_role_ids": sorted({str(role.id) for role in source.role_mentions}),
        }
        role_ids = set(sticky["allowed_role_ids"])
        role_ids.update(role_ids_in(content))
        sticky["allowed_role_ids"] = sorted(role_ids)

        await interaction.response.defer(ephemeral=True)
        try:
            sent = await post_sticky(channel, sticky)
        except discord.HTTPException:
            return await interaction.followup.send(
                "I couldn't repost that message. Check that I can send embeds and links here.",
                ephemeral=True,
            )

        data = load_sticky_data()
        previous = data.get(str(channel.id), {})
        sticky["messageId"] = str(sent.id)
        data[str(channel.id)] = sticky
        save_sticky_data(data)
        await delete_old_sticky(channel, previous.get("messageId"))
        await interaction.followup.send(
            "✅ That message is now the sticky for this channel.", ephemeral=True
        )

    @app_commands.command(name="view", description="View this channel's sticky message")
    async def view(self, interaction: discord.Interaction):
        current = load_sticky_data().get(str(interaction.channel.id))
        if not current:
            return await interaction.response.send_message(
                "There is no sticky message set in this channel.",
                ephemeral=True,
            )

        summary = current.get("content") or ""
        if current.get("embeds"):
            summary += f"\n📎 {len(current['embeds'])} embed(s)"
        if current.get("buttons"):
            summary += f"\n🔗 {len(current['buttons'])} link button(s)"
        await interaction.response.send_message(
            f"📌 Current sticky message:\n{summary or '(embed content)'}",
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
