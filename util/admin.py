import fluxer

ADMINISTRATOR = 0x8


async def is_admin(bot: fluxer.Client, message: fluxer.Message) -> bool:
    """
    Check if the author of the message has administrator permissions in the guild.
    This is done by fetching the member's roles and checking if any of them have the administrator permission bit set.

    Args:
        bot: The bot instance
        message: The message to check permissions for
    """
    guild = await bot.fetch_guild(str(message.guild_id)) if message.guild_id else None
    if guild is None:
        return False

    # Ignoring type on this because the library's type hints aren't accurate
    member: fluxer.GuildMember = await guild.fetch_member(message.author.id)  # type: ignore

    if message.guild_id is None or bot._http is None:
        return False
    guild_roles = await bot._http.get_guild_roles(message.guild_id)

    # Loop through the guild roles and check if the member has any role with administrator permissions
    for role in guild_roles:
        if int(role["id"]) in member.roles and int(role["permissions"]) & ADMINISTRATOR:
            return True

    return False
