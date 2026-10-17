import logging
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from monitoring import MonitorFormButton

log = logging.getLogger("amaya.deliver")

# ====== EDIT THESE ======
SERVER_NAME_LINK = "https://discord.com/invite/EsWBG4kA76"
SHOW_SERVER_CARD = False  # False = no embeds under the message (True = show the invite cards)
FORM_EMOJI = "<:035:1498665804688916520>"
VOUCH_EMOJI = "<:023:1498665355512381593>"
# ========================

B = "\u2800"  # invisible blank character
LINK = SERVER_NAME_LINK if SHOW_SERVER_CARD else f"<{SERVER_NAME_LINK}>"

HEADER_LINE = (
    f"_ _ {B}{B}**delivery from [ 猫 amaya ♡]({LINK})**  <:040:1498665961354694767>  "
)


def clean(s: str) -> str:
    return s.replace("`", "'")


def build_account_message(item, email, password, profile, monitoring) -> str:
    lines = [
        HEADER_LINE,
        "_ _  ·  thank   you for  choosing  amaya !",
        "_ _  ·  please  check your account  asap",
        "_ _  ·  report   issues   through  a  ticket",
        "_ _  ·  keep  your  login   details  private",
        "_ _  ·  vouch within  10 hrs for warranty",
        "",
        f"_ _ {B}📎    {B}—{B} *{item}*",
        f"_ _ 💌    : `{clean(email)}`",
        f"_ _ 🗝️    : `{clean(password)}`",
        f"_ _ 🎫    : `{clean(profile)}`",
    ]
    if monitoring:
        lines += [
            "",
            f"**-# {B}__no form & proof of login = voided warranty__**",
            "_ _  **to fully activate your warranty** for ",
            "_ _  netpliks,  hbiow,  and  disney  items, ",
            "_ _  kindly submit your monitoring form.",
        ]
    return "\n".join(lines)


def build_custom_message(item, details, style, note) -> str:
    body = details if style == "plain" else f"`{clean(details)}`"
    lines = [
        HEADER_LINE,
        "_ _  ·  thank   you for  choosing  amaya !",
        "_ _  ·  please  check your item  asap",
        "_ _  ·  report   issues   through  a  ticket",
        "_ _  ·  keep  your  item   private",
        "_ _  ·  vouch within  10 hrs for warranty",
        "",
        f"_ _ {B}📎    {B}—{B} *{item}*",
        f"_ _ 🎁    : {body}",
    ]
    if note:
        lines += ["", f"_ _ 💬    : {note}"]
    return "\n".join(lines)


def build_view(with_form: bool) -> Optional[discord.ui.View]:
    view = discord.ui.View(timeout=None)
    if with_form:
        view.add_item(MonitorFormButton(emoji=FORM_EMOJI))

    vouch_url = os.getenv("VOUCH_CHANNEL_URL")
    if vouch_url and vouch_url.startswith("http"):
        view.add_item(
            discord.ui.Button(
                label="drop your vouch here",
                emoji=VOUCH_EMOJI,
                style=discord.ButtonStyle.link,
                url=vouch_url,
            )
        )
    return view if view.children else None


def utf16_len(s: str) -> int:
    # Match the old JS `.length` (UTF-16 units) so the 2000-char check behaves the same
    return len(s.encode("utf-16-le")) // 2


@app_commands.default_permissions(manage_messages=True)
class Deliver(commands.GroupCog, name="deliver", description="Send a purchased item to a customer's DMs"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    # ---------- shared sending logic ----------
    async def _deliver(self, interaction, sub, user, item, content, with_form):
        if utf16_len(content) > 2000:
            return await interaction.response.send_message(
                "❌ That message is too long for a DM (2000 character limit).",
                ephemeral=True,
            )

        # Tell staff (privately) if something isn't configured, instead of silently skipping it
        warnings = []
        vouch_url = os.getenv("VOUCH_CHANNEL_URL")
        if not vouch_url or not vouch_url.startswith("http"):
            warnings.append("⚠️ Vouch button was left out: `VOUCH_CHANNEL_URL` is missing or isn't a link.")
        if with_form and not os.getenv("MONITORING_CHANNEL_ID"):
            warnings.append("⚠️ `MONITORING_CHANNEL_ID` isn't set, so the monitoring form won't submit.")

        await interaction.response.defer(ephemeral=True)

        try:
            view = build_view(with_form)
            kwargs = {"view": view} if view else {}
            await user.send(
                content, allowed_mentions=discord.AllowedMentions.none(), **kwargs
            )
        except discord.Forbidden as err:
            if err.code == 50007:
                return await interaction.followup.send(
                    f"❌ Couldn't DM {user.mention}. Their DMs are closed. Ask them to enable DMs "
                    "from server members, then run the command again.",
                    ephemeral=True,
                )
            log.error("❌ Deliver DM failed: %s", err)
            return await interaction.followup.send(
                "❌ Something went wrong sending the DM.", ephemeral=True
            )
        except Exception as err:
            log.error("❌ Deliver DM failed: %s", err)
            return await interaction.followup.send(
                "❌ Something went wrong sending the DM.", ephemeral=True
            )

        # Optional log. Never includes passwords/codes, only who/what.
        log_id = os.getenv("DELIVERY_LOG_CHANNEL_ID")
        if log_id:
            try:
                log_channel = await interaction.client.fetch_channel(int(log_id))
                embed = discord.Embed(color=0x57F287, title="✅ Order Delivered")
                embed.add_field(name="Customer", value=f"{user.mention} ({user})", inline=True)
                embed.add_field(name="Delivered by", value=interaction.user.mention, inline=True)
                embed.add_field(name="Type", value=sub, inline=True)
                embed.add_field(name="Item", value=item, inline=False)
                embed.timestamp = discord.utils.utcnow()
                await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except Exception as err:
                log.error("❌ Delivery log failed: %s", err)

        await interaction.followup.send(
            "\n".join([f"✅ Delivered **{item}** to {user.mention}'s DMs.", *warnings]),
            ephemeral=True,
        )

    # ---------- /deliver account ----------
    @app_commands.command(name="account", description="Deliver an account (email, password, profile)")
    @app_commands.describe(
        user="Who bought it",
        item="e.g. one m. sl. netpliks",
        email="Account email",
        password="Account password",
        profile="Profile / PIN (leave empty for n/a)",
        monitoring="Include the warranty monitoring form button (default: yes)",
    )
    async def account(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        item: str,
        email: str,
        password: str,
        profile: Optional[str] = None,
        monitoring: Optional[bool] = None,
    ):
        if user.bot:
            return await interaction.response.send_message(
                "❌ You can't deliver to a bot.", ephemeral=True
            )
        with_form = True if monitoring is None else monitoring
        content = build_account_message(item, email, password, profile or "n/a", with_form)
        await self._deliver(interaction, "account", user, item, content, with_form)

    # ---------- /deliver custom ----------
    @app_commands.command(name="custom", description="Deliver anything else (nitro, codes, links...)")
    @app_commands.describe(
        user="Who bought it",
        item="Item name",
        details="The code/link/etc. (type \\n for a new line)",
        style="How to show it (default: code, easy to copy)",
        note="Optional message to the customer",
    )
    @app_commands.choices(
        style=[
            app_commands.Choice(name="Code (easy to copy)", value="code"),
            app_commands.Choice(name="Plain (links stay clickable)", value="plain"),
        ]
    )
    async def custom(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        item: str,
        details: str,
        style: Optional[app_commands.Choice[str]] = None,
        note: Optional[str] = None,
    ):
        if user.bot:
            return await interaction.response.send_message(
                "❌ You can't deliver to a bot.", ephemeral=True
            )
        content = build_custom_message(
            item,
            details.replace("\\n", "\n"),
            style.value if style else "code",
            note,
        )
        await self._deliver(interaction, "custom", user, item, content, False)


async def setup(bot):
    await bot.add_cog(Deliver(bot))
