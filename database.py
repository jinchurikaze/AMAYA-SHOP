import logging
import os

from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("amaya.db")

_client = None
_db = None


async def connect():
    """Connect to MongoDB. Raises on failure (main.py exits, like the old bot)."""
    global _client, _db
    uri = os.getenv("MONGO_URI")
    if not uri:
        raise RuntimeError("MONGO_URI is missing in your environment / .env file")

    _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=10_000)
    await _client.admin.command("ping")
    _db = _client.get_default_database(default="amaya-bot")
    log.info("✅ MongoDB connected")
    return _db


def get_db():
    if _db is None:
        raise RuntimeError("Database not connected yet")
    return _db
