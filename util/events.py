import logging

from fluxer.http import HTTPClient, Route


async def handle_reaction(
    http: HTTPClient, guild_id: int, user_id: int, role_id: int, added: bool
) -> None:
    method = "PUT" if added else "DELETE"
    route = Route(
        method,
        "/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
        guild_id=guild_id,
        user_id=user_id,
        role_id=role_id,
    )
    try:
        await http.request(route)
    except Exception as e:
        logging.error(f"Error handling reaction: {e}")
