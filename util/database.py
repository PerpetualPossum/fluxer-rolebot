from tinydb import TinyDB, Query
import os

Database = TinyDB(os.getenv("DB_PATH", "db.json"))
roles_table = Database.table("roles")
message_table = Database.table("message")


def set_role_association(guild_id: int, role_id: int, emoji: str) -> None:
    Guild = Query()
    roles_table.upsert(
        {"guild_id": guild_id, "role_id": role_id, "emoji": emoji},
        (Guild.guild_id == guild_id) & (Guild.emoji == emoji),
    )


def get_role_association(guild_id: int, emoji: str) -> int | None:
    Guild = Query()
    result = roles_table.search((Guild.guild_id == guild_id) & (Guild.emoji == emoji))
    return result[0]["role_id"] if result else None


def set_configured_message(
    guild_id: int, channel_id: int, message_id: int
) -> None:
    Guild = Query()
    message_table.upsert(
        {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "configured_message_id": message_id,
        },
        Guild.guild_id == guild_id,
    )


def get_configured_message(guild_id: int) -> dict | None:
    Guild = Query()
    result = message_table.search(
        (Guild.guild_id == guild_id) & (Guild.configured_message_id.exists())
    )
    if not result:
        return None
    return {
        "channel_id": result[0]["channel_id"],
        "message_id": result[0]["configured_message_id"],
    }


def delete_role_association(guild_id: int, emoji: str) -> bool:
    Guild = Query()
    removed = roles_table.remove(
        (Guild.guild_id == guild_id) & (Guild.emoji == emoji)
    )
    return len(removed) > 0


def delete_configured_message_id(guild_id: int) -> bool:
    Guild = Query()
    removed = message_table.remove(Guild.guild_id == guild_id)
    return len(removed) > 0
