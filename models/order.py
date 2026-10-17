from datetime import datetime, timezone

from bson import ObjectId

from database import get_db


# Same collection name Mongoose used for model "Order", so existing data still works.
def _col():
    return get_db()["orders"]


async def create_order(*, user_id, username, item, quantity, price, payment) -> dict:
    doc = {
        "userId": str(user_id),
        "username": username,
        "item": item,
        "quantity": quantity,
        "price": price,
        "payment": payment,
        "status": "noted",
        "createdAt": datetime.now(timezone.utc),
    }
    result = await _col().insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def set_message_id(order_id, message_id) -> None:
    await _col().update_one(
        {"_id": ObjectId(str(order_id))}, {"$set": {"messageId": str(message_id)}}
    )


async def set_status(order_id, status: str) -> None:
    await _col().update_one({"_id": ObjectId(str(order_id))}, {"$set": {"status": status}})


async def set_status_by_message(message_id, status: str) -> None:
    await _col().update_one({"messageId": str(message_id)}, {"$set": {"status": status}})