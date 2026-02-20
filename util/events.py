import logging

import fluxer


async def handle_reaction(
    bot: fluxer.Client,
    guild_id: int,
    user_id: int,
    role_id: int,
    added: bool,
) -> None:
    if bot._http is None:
        logging.error("Error handling reaction: HTTP client is not available.")
        return
    guild = await bot.fetch_guild(str(guild_id))

    # Ignoring type on this because the library's type hints aren't accurate
    member: fluxer.GuildMember = await guild.fetch_member(user_id) if guild else None  # type: ignore
    if member is None:
        logging.error(
            f"Error handling reaction: Member {user_id} not found in guild {guild_id}."
        )
        return

    if member.user.bot:
        return  # Ignore bot reactions

    if added:
        logging.info(f"Adding role {role_id} to user {user_id} in guild {guild_id}")
        await member.add_role(role_id, guild_id=guild_id)
    else:
        logging.info(f"Removing role {role_id} from user {user_id} in guild {guild_id}")
        if role_id in member.roles:
            try:
                await member.remove_role(role_id, guild_id=guild_id)
            except RuntimeError as e:
                logging.error(
                    f"Attempted to remove rule {role_id} from user {user_id} but encountered an error: {e}. This likely means they didn't have the role."
                )

        else:
            logging.warning(f"Role {role_id} not found in user {user_id}'s roles.")
