import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("amaya.eligible")

# Configuration
GROUPS_TO_CHECK = [
    {"id": 34319686, "name": "Jin's UGC"},
    {"id": 34162917, "name": "/affinity"},
    {"id": 396199818, "name": "Orquidea"},
    {"id": 35753423, "name": "PATHINGTON"},
    {"id": 34323970, "name": "Fiji's Domain"},
    {"id": 35515467, "name": "猫 amaya"},
]

DAYS_REQUIRED = 14
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "memberTracking.json"

DATE_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$", re.ASCII)


def now_ms() -> int:
    return int(time.time() * 1000)


def load_tracking_data() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        return {}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception as err:
        log.error("Error loading tracking data: %s", err)
        return {}


def save_tracking_data(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as err:
        log.error("Error saving tracking data: %s", err)


def get_days_since(timestamp_ms: int) -> int:
    return (now_ms() - timestamp_ms) // (1000 * 60 * 60 * 24)


def parse_date(date_str: Optional[str]) -> Optional[int]:
    """MM-DD-YYYY -> epoch ms (UTC). None if invalid or in the future."""
    if not date_str:
        return None
    m = DATE_RE.match(date_str)
    if not m:
        return None
    month, day, year = (int(x) for x in m.groups())
    try:
        dt = datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None
    ms = int(dt.timestamp() * 1000)
    if ms > now_ms():
        return None
    return ms


def format_date(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}"


def err_embed(text: str) -> discord.Embed:
    return discord.Embed(description=text, color=0xED4245)


def build_embed(username, display_name, user_id, user_groups, tracking_data):
    lines = []
    groups_not_in = []

    for cfg in GROUPS_TO_CHECK:
        link = f"[{cfg['name']}](https://www.roblox.com/groups/{cfg['id']})"
        membership = next((g for g in user_groups if g["group"]["id"] == cfg["id"]), None)

        if not membership:
            lines.append(f"{link} : **Not in Group**")
            groups_not_in.append(cfg)
            continue

        entry = tracking_data.get(f"{user_id}_{cfg['id']}")
        if not entry:
            lines.append(f"{link} : **In Group** (not yet tracked)")
            continue

        days = get_days_since(entry["firstSeen"])
        joined = format_date(entry["firstSeen"])
        if days >= DAYS_REQUIRED:
            lines.append(f"{link} : **Eligible Joined {joined}**")
        else:
            lines.append(f"{link} : Joined {joined} **({days}/{DAYS_REQUIRED} days)**")

    embed = discord.Embed(title=f"{display_name} ?", description="\n".join(lines), color=0x2B2D31)
    embed.set_thumbnail(
        url=f"https://www.roblox.com/headshot-thumbnail/image?userId={user_id}&width=150&height=150&format=png"
    )
    embed.timestamp = discord.utils.utcnow()
    return embed, groups_not_in


def join_view(groups_not_in) -> Optional[discord.ui.View]:
    if not groups_not_in:
        return None
    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="Join our Roblox Group",
            style=discord.ButtonStyle.link,
            url=f"https://www.roblox.com/groups/{groups_not_in[0]['id']}",
            emoji="🔗",
        )
    )
    return view


class OverrideView(discord.ui.View):
    """Yes/No confirmation for replacing an existing join date (expires after 60s)."""

    def __init__(self, *, owner_id, tracking_key, override_ts, user_id, username,
                 display_name, user_groups, group_name):
        super().__init__(timeout=60)
        self.owner_id = owner_id
        self.tracking_key = tracking_key
        self.override_ts = override_ts
        self.user_id = user_id
        self.username = username
        self.display_name = display_name
        self.user_groups = user_groups
        self.group_name = group_name
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ Only the person who ran the command can answer this.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except Exception:
                pass

    @discord.ui.button(label="Yes, Override", style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        data = load_tracking_data()
        entry = data.get(self.tracking_key, {})
        entry["firstSeen"] = self.override_ts
        data[self.tracking_key] = entry
        save_tracking_data(data)

        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"✅ Join date set for **{self.username}** in **{self.group_name}**: "
                            f"{format_date(self.override_ts)}",
                color=0x57F287,
            ),
            view=None,
        )
        await asyncio.sleep(1.5)
        embed, not_in = build_embed(
            self.username, self.display_name, self.user_id, self.user_groups, load_tracking_data()
        )
        view = join_view(not_in)
        await interaction.followup.send(embed=embed, **({"view": view} if view else {}))

    @discord.ui.button(label="No, Keep Existing", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(description="👍 Kept the existing join date.", color=0x2B2D31),
            view=None,
        )


class Eligible(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="eligible", description="Check if a Roblox user is eligible for Robux payout")
    @app_commands.describe(
        username="Roblox username to check",
        groupname="Group to set/override join date for",
        joindate="Join date for the specified group (format: MM-DD-YYYY, e.g., 01-15-2025)",
    )
    @app_commands.choices(
        groupname=[app_commands.Choice(name=g["name"], value=str(g["id"])) for g in GROUPS_TO_CHECK]
    )
    async def eligible(
        self,
        interaction: discord.Interaction,
        username: str,
        groupname: Optional[app_commands.Choice[str]] = None,
        joindate: Optional[str] = None,
    ):
        await interaction.response.defer()

        group_id_override = groupname.value if groupname else None
        tracking = load_tracking_data()

        # joindate requires groupname
        if joindate and not group_id_override:
            return await interaction.edit_original_response(
                embed=err_embed("❌ Please select a **groupname** when specifying a join date.")
            )

        # date format
        if joindate and parse_date(joindate) is None:
            return await interaction.edit_original_response(
                embed=err_embed(
                    "❌ Invalid date format. Please use **MM-DD-YYYY** (e.g., `01-15-2025`)\n\n"
                    "Make sure the date is valid and not in the future."
                )
            )

        session = self.bot.session
        try:
            # username -> user ID
            async with session.post(
                "https://users.roblox.com/v1/usernames/users",
                json={"usernames": [username], "excludeBannedUsers": False},
            ) as resp:
                resp.raise_for_status()
                users = (await resp.json()).get("data") or []

            if not users:
                return await interaction.edit_original_response(
                    embed=err_embed(f"❌ Could not find Roblox user: **{username}**")
                )

            user_id = users[0]["id"]
            display_name = users[0]["displayName"]

            # user's groups
            async with session.get(
                f"https://groups.roblox.com/v1/users/{user_id}/groups/roles"
            ) as resp:
                resp.raise_for_status()
                user_groups = (await resp.json())["data"]

            # auto-track new memberships
            for cfg in GROUPS_TO_CHECK:
                membership = next((g for g in user_groups if g["group"]["id"] == cfg["id"]), None)
                if not membership:
                    continue
                key = f"{user_id}_{cfg['id']}"
                if key not in tracking:
                    tracking[key] = {
                        "userId": user_id,
                        "username": username,
                        "groupId": cfg["id"],
                        "groupName": cfg["name"],
                        "firstSeen": now_ms(),
                        "role": membership["role"]["name"],
                        "rank": membership["role"]["rank"],
                    }
                    save_tracking_data(tracking)

            # manual join date override
            if joindate and group_id_override:
                override_ts = parse_date(joindate)
                key = f"{user_id}_{group_id_override}"
                cfg = next(g for g in GROUPS_TO_CHECK if str(g["id"]) == str(group_id_override))
                membership = next((g for g in user_groups if g["group"]["id"] == cfg["id"]), None)

                if not membership:
                    return await interaction.edit_original_response(
                        embed=err_embed(
                            f"❌ **{username}** is not a member of **{cfg['name']}**. "
                            "Cannot set join date for a group they're not in."
                        )
                    )

                if key in tracking:
                    view = OverrideView(
                        owner_id=interaction.user.id,
                        tracking_key=key,
                        override_ts=override_ts,
                        user_id=user_id,
                        username=username,
                        display_name=display_name,
                        user_groups=user_groups,
                        group_name=cfg["name"],
                    )
                    embed = discord.Embed(
                        title="⚠️ Existing Join Date Found",
                        description=(
                            f"**{username}** already has a tracked join date for **{cfg['name']}**.\n\n"
                            f"**Current Join Date:** {format_date(tracking[key]['firstSeen'])}\n"
                            f"**New Join Date:** {format_date(override_ts)}\n\n"
                            "Do you want to override the existing date?"
                        ),
                        color=0xFEE75C,
                    )
                    view.message = await interaction.edit_original_response(embed=embed, view=view)
                    return

                # no existing data -> apply directly
                tracking[key] = {
                    "userId": user_id,
                    "username": username,
                    "groupId": cfg["id"],
                    "groupName": cfg["name"],
                    "firstSeen": override_ts,
                    "role": membership["role"]["name"],
                    "rank": membership["role"]["rank"],
                }
                save_tracking_data(tracking)

                await interaction.edit_original_response(
                    embed=discord.Embed(
                        description=f"✅ Join date set for **{username}** in **{cfg['name']}**: "
                                    f"{format_date(override_ts)}",
                        color=0x57F287,
                    )
                )
                await asyncio.sleep(1.5)
                embed, not_in = build_embed(username, display_name, user_id, user_groups, load_tracking_data())
                view = join_view(not_in)
                await interaction.followup.send(embed=embed, **({"view": view} if view else {}))
                return

            # default: show eligibility status
            embed, not_in = build_embed(username, display_name, user_id, user_groups, load_tracking_data())
            view = join_view(not_in)
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception:
            log.exception("Error in eligible command")
            await interaction.edit_original_response(
                embed=err_embed("❌ An error occurred while checking the user. Please try again.")
            )


async def setup(bot):
    await bot.add_cog(Eligible(bot))
