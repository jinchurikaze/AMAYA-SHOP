"""Register slash commands to your guild.   Run:  python deploy_commands.py"""
import asyncio
import logging
import os
import sys

import discord
from dotenv import load_dotenv

load_dotenv()

from main import AmayaBot  # noqa: E402


def need(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"❌ {name} is missing in .env file!")
        sys.exit(1)
    return value


async def deploy():
    token = need("BOT_TOKEN")
    need("CLIENT_ID")
    guild_id = int(need("GUILD_ID"))

    bot = AmayaBot(deploy_only=True)
    async with bot:
        try:
            await bot.login(token)  # also runs setup_hook -> loads cogs only
            guild = discord.Object(id=guild_id)

            print(f"\n🔄 Refreshing {len(bot.tree.get_commands())} application (/) commands...")
            print(f"📍 Client ID: {os.getenv('CLIENT_ID')}")
            print(f"📍 Guild ID: {guild_id}\n")

            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)

            print(f"✅ Successfully registered {len(synced)} application commands!")
            print("\n📋 Registered commands:")
            for cmd in synced:
                print(f"   - /{cmd.name}: {cmd.description}")

        except discord.LoginFailure:
            print("\n🔑 Unauthorized - Your BOT_TOKEN is invalid or expired.")
            print("   → Discord Developer Portal → Bot tab → Reset Token → update .env")
            sys.exit(1)
        except discord.HTTPException as err:
            if err.code == 50001:
                print("\n🚫 Missing Access - Bot is not in the guild. Re-invite your bot.")
            elif err.code == 10004:
                print("\n🔍 Unknown Guild - GUILD_ID is incorrect. Right-click server → Copy Server ID.")
            else:
                print(f"\n❌ Error deploying commands: {err}")
            sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(deploy())
