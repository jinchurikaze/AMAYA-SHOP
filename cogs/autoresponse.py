import discord
from discord import app_commands
from discord.ext import commands

from database import get_db


@app_commands.default_permissions(manage_messages=True)
@app_commands.guild_only()
class AutoResponse(commands.GroupCog, name="autoresponse", description="Manage automatic responses"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="add", description="Add or replace an automatic response")
    @app_commands.describe(trigger="Text that activates the response", response="Response to send")
    async def add(self, interaction: discord.Interaction, trigger: str, response: str):
        trigger = trigger.strip()
        response = response.strip()
        if not trigger or len(trigger) > 80:
            return await interaction.response.send_message(
                "Trigger must be between 1 and 80 characters.", ephemeral=True
            )
        if not response or len(response) > 1800:
            return await interaction.response.send_message(
                "Response must be between 1 and 1800 characters.", ephemeral=True
            )

        await get_db()["auto_responses"].update_one(
            {"guild_id": str(interaction.guild_id), "trigger_key": trigger.casefold()},
            {"$set": {
                "guild_id": str(interaction.guild_id),
                "trigger": trigger,
                "trigger_key": trigger.casefold(),
                "response": response,
                "updated_by": str(interaction.user.id),
            }},
            upsert=True,
        )
        await interaction.response.send_message(
            f"✅ Auto-response saved for **{trigger}**.", ephemeral=True
        )

    @app_commands.command(name="remove", description="Remove an automatic response")
    @app_commands.describe(trigger="The trigger to remove")
    async def remove(self, interaction: discord.Interaction, trigger: str):
        result = await get_db()["auto_responses"].delete_one({
            "guild_id": str(interaction.guild_id),
            "trigger_key": trigger.strip().casefold(),
        })
        message = "✅ Auto-response removed." if result.deleted_count else "No matching trigger was found."
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="list", description="List this server's automatic responses")
    async def list_(self, interaction: discord.Interaction):
        entries = await get_db()["auto_responses"].find(
            {"guild_id": str(interaction.guild_id)}
        ).sort("trigger_key", 1).to_list(length=10)
        if not entries:
            return await interaction.response.send_message(
                "No auto-responses are configured.", ephemeral=True
            )
        lines = [
            f"• **{entry['trigger']}** → {entry['response'][:100]}"
            for entry in entries
        ]
        if len(entries) == 10:
            lines.append("Showing the first 10 triggers.")
        await interaction.response.send_message(
            "\n".join(lines), ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or not message.content:
            return

        entries = await get_db()["auto_responses"].find(
            {"guild_id": str(message.guild.id)}
        ).to_list(length=100)
        content = message.content.casefold()
        matches = [
            entry for entry in entries
            if entry.get("trigger_key") and entry["trigger_key"] in content
        ]
        if not matches:
            return

        # Use the longest matching trigger to avoid a shorter trigger winning by accident.
        match = max(matches, key=lambda entry: len(entry["trigger_key"]))
        await message.reply(
            match["response"],
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot):
    await bot.add_cog(AutoResponse(bot))
