import os
import re
import fluxer
import logging
import emoji
from dotenv import load_dotenv
from util.events import handle_reaction
from fluxer.http import Route
from util.database import (
    set_role_association,
    get_role_association,
    delete_role_association,
    set_configured_message,
    get_configured_message,
    delete_configured_message_id,
)

logging.basicConfig(level=logging.INFO)
load_dotenv()

bot = fluxer.Bot(
    command_prefix=os.getenv("COMMAND_PREFIX", "!role"), intents=fluxer.Intents.all()
)


###
# Helpers
###


ADMINISTRATOR = 0x8


async def is_admin(message: fluxer.Message) -> bool:
    if message.guild_id is None or bot._http is None:
        return False
    member_data = await bot._http.get_guild_member(message.guild_id, message.author.id)
    member_roles = {int(r) for r in member_data.get("roles", [])}
    guild_roles = await bot._http.get_guild_roles(message.guild_id)
    for role in guild_roles:
        if int(role["id"]) in member_roles and int(role["permissions"]) & ADMINISTRATOR:
            return True
    return False


def clean_reaction_emoji(emoji_data: dict) -> str:
    """Convert raw gateway emoji dict to our stored format."""
    if emoji_data.get("id") is not None:
        return f":{emoji_data['name']}:"
    return emoji.demojize(emoji_data["name"])


def parse_emoji(text: str) -> str:
    custom_match = re.search(r"<:(\w+):\d+>", text)
    if custom_match:
        return f":{custom_match.group(1)}:"
    return emoji.demojize(text.split()[0])


def emoji_for_reaction_api(text: str) -> str:
    """Convert raw emoji text to the format the reaction API expects.

    Unicode emoji: the actual character (aiohttp handles URL encoding).
    Custom emoji: name:id format.
    """
    custom_match = re.search(r"<:(\w+):(\d+)>", text)
    if custom_match:
        return f"{custom_match.group(1)}:{custom_match.group(2)}"
    return emoji.emojize(text.strip())


def get_reaction_role_id(
    guild_id: int, user_id: int, message_id: int, emoji_str: str
) -> int | None:
    if bot.user is None or user_id == bot.user.id:
        return None

    configured = get_configured_message(guild_id)
    if configured is None or message_id != configured["message_id"]:
        return None

    return get_role_association(guild_id, emoji_str)


###
# Events
###


@bot.event
async def on_ready():
    if bot.user is not None:
        logging.info(f"Logged in as {bot.user.username}")
    else:
        logging.warning("Failed to log in, but on_ready was called.")


@bot.event
async def on_message_reaction_add(data):
    guild_id = int(data["guild_id"])
    user_id = int(data["user_id"])
    message_id = int(data["message_id"])
    cleaned = clean_reaction_emoji(data["emoji"])
    role_id = get_reaction_role_id(guild_id, user_id, message_id, cleaned)
    if role_id is not None and bot._http is not None:
        await handle_reaction(bot._http, guild_id, user_id, role_id, added=True)


@bot.event
async def on_message_reaction_remove(data):
    guild_id = int(data["guild_id"])
    user_id = int(data["user_id"])
    message_id = int(data["message_id"])
    cleaned = clean_reaction_emoji(data["emoji"])
    role_id = get_reaction_role_id(guild_id, user_id, message_id, cleaned)
    if role_id is not None and bot._http is not None:
        await handle_reaction(bot._http, guild_id, user_id, role_id, added=False)


###
# Commands
###


@bot.command(name="setmessage")
async def set_message_cmd(message: fluxer.Message):
    if message.guild_id is None:
        await message.reply("This command can only be used in a server.")
        return

    if not await is_admin(message):
        await message.reply("You need administrator permissions to use this command.")
        return

    link_match = re.search(r"channels/(\d+)/(\d+)/(\d+)", message.content)
    if link_match is None:
        await message.reply("Usage: `!role setmessage <message_link>`")
        return

    channel_id = int(link_match.group(2))
    msg_id = int(link_match.group(3))
    set_configured_message(message.guild_id, channel_id, msg_id)
    await message.reply(f"Set role react message to `{msg_id}` in <#{channel_id}>.")


@bot.command(name="removemessage")
async def remove_message_cmd(message: fluxer.Message):
    if message.guild_id is None:
        await message.reply("This command can only be used in a server.")
        return

    if not await is_admin(message):
        await message.reply("You need administrator permissions to use this command.")
        return

    if get_configured_message(message.guild_id) is None:
        await message.reply("No role react message is configured for this server.")
        return

    delete_configured_message_id(message.guild_id)
    await message.reply("Removed the role react message configuration.")


@bot.command(name="add")
async def add_emoji_cmd(message: fluxer.Message):
    if message.guild_id is None:
        await message.reply("This command can only be used in a server.")
        return

    if not await is_admin(message):
        await message.reply("You need administrator permissions to use this command.")
        return

    configured = get_configured_message(message.guild_id)
    if configured is None:
        await message.reply(
            "No role react message is configured. Use `!role setmessage <message_link>` first."
        )
        return

    role_match = re.search(r"<@&(\d+)>", message.content)
    if role_match is None:
        await message.reply("Please mention a role. Usage: `!role add @Role :emoji:`")
        return

    role_id = int(role_match.group(1))

    after_role = message.content[role_match.end() :].strip()
    if not after_role:
        await message.reply("Please provide an emoji. Usage: `!role add @Role :emoji:`")
        return

    cleaned = parse_emoji(after_role)

    if get_role_association(message.guild_id, cleaned) is not None:
        await message.reply(
            "That emoji is already associated with a role in this server."
        )
        return

    set_role_association(message.guild_id, role_id, cleaned)

    if bot._http is not None:
        api_emoji = emoji_for_reaction_api(after_role)
        route = Route(
            "PUT",
            "/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me",
            channel_id=configured["channel_id"],
            message_id=configured["message_id"],
            emoji=api_emoji,
        )
        logging.info(f"Adding reaction: emoji={api_emoji!r} url={route.url}")
        try:
            await bot._http.request(route)
        except Exception as e:
            errors = getattr(e, "errors", [])
            logging.error(f"Failed to add reaction: {e} errors={errors}")
            await message.reply(
                f"Associated {after_role.split()[0]} with <@&{role_id}>, but failed to add reaction to message."
            )
            return

    await message.reply(f"Associated {after_role.split()[0]} with <@&{role_id}>.")


@bot.command(name="remove")
async def remove_emoji_cmd(message: fluxer.Message):
    if message.guild_id is None:
        await message.reply("This command can only be used in a server.")
        return

    if not await is_admin(message):
        await message.reply("You need administrator permissions to use this command.")
        return

    if get_configured_message(message.guild_id) is None:
        await message.reply(
            "No role react message is configured. Use `!role setmessage <message_link>` first."
        )
        return

    after_cmd = message.content.split("remove", 1)[-1].strip()
    if not after_cmd:
        await message.reply("Usage: `!role remove :emoji:`")
        return

    cleaned = parse_emoji(after_cmd)

    if not delete_role_association(message.guild_id, cleaned):
        await message.reply("That emoji is not associated with any role.")
        return

    await message.reply(f"Removed role association for {after_cmd.split()[0]}.")


if __name__ == "__main__":
    bot.run(os.getenv("FLUXER_TOKEN", ""))
