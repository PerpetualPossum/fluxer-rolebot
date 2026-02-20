import re
import emoji
import fluxer
from fluxer import Cog

from util.admin import is_admin
from util.database import (
    delete_role_association,
    get_configured_message,
    get_role_association,
    set_role_association,
)
from util.events import handle_reaction

from logging import getLogger

logger = getLogger(__name__)


def clean_reaction_emoji(emoji_data: fluxer.models.PartialEmoji) -> str:
    """
    Convert a PartialEmoji to the stored format.

    Args:
        emoji_data: The PartialEmoji from the gateway event
    """
    if emoji_data.id is not None:
        return f":{emoji_data.name}:"
    return emoji.demojize(emoji_data.name or "")


def parse_emoji(text: str) -> str:
    """
    Convert user input emoji text to the stored format.
    Handles both unicode and custom emoji formats.

    Args:
        text: The raw emoji text input by the user
    """
    custom_match = re.search(r"<:(\w+):\d+>", text)
    if custom_match:
        return f":{custom_match.group(1)}:"
    return emoji.demojize(text.split()[0])


def emoji_for_reaction_api(text: str) -> str:
    """
    Convert raw emoji text to the format the reaction API expects.

    Unicode emoji: the actual character (aiohttp handles URL encoding).
    Custom emoji: name:id format.

    Args:
        text: The raw emoji text input by the user
    """
    custom_match = re.search(r"<:(\w+):(\d+)>", text)
    if custom_match:
        return f"{custom_match.group(1)}:{custom_match.group(2)}"
    return emoji.emojize(text.strip())


def get_reaction_role_id(
    bot: fluxer.Client, guild_id: int, user_id: int, message_id: int, emoji_str: str
) -> int | None:
    """
    Check if the reaction corresponds to a configured role reaction and return the associated role ID.
    Also performs checks to ensure the reaction is on the configured message and not from a bot.

    Args:
        guild_id: The ID of the guild where the reaction occurred
        user_id: The ID of the user who reacted
        message_id: The ID of the message that was reacted to
        emoji_str: The cleaned emoji string that was reacted with
    """
    if bot.user is None or user_id == bot.user.id:
        return None

    configured = get_configured_message(guild_id)
    if configured is None or message_id != configured["message_id"]:
        return None

    return get_role_association(guild_id, emoji_str)


class ReactionHandling(Cog):
    def __init__(self, bot: fluxer.Bot):
        super().__init__(bot)

    @Cog.listener()
    async def on_raw_reaction_add(self, ctx: fluxer.models.RawReactionActionEvent):
        """
        Handle a reaction being added to a message. Checks if the reaction corresponds to a configured role reaction and adds the role if so.
        """
        guild_id = ctx.guild_id
        user_id = ctx.user_id
        message_id = ctx.message_id

        if guild_id is None:
            return

        cleaned = clean_reaction_emoji(ctx.emoji)
        role_id = get_reaction_role_id(self.bot, guild_id, user_id, message_id, cleaned)
        if role_id is not None:
            await handle_reaction(self.bot, guild_id, user_id, role_id, added=True)

    @Cog.listener()
    async def on_raw_reaction_remove(self, ctx: fluxer.models.RawReactionActionEvent):
        """
        Handle a reaction being removed from a message. Checks if the reaction corresponds to a configured role reaction and removes the role if so.
        """
        guild_id = ctx.guild_id
        user_id = ctx.user_id
        message_id = ctx.message_id

        if guild_id is None:
            return

        cleaned = clean_reaction_emoji(ctx.emoji)
        role_id = get_reaction_role_id(self.bot, guild_id, user_id, message_id, cleaned)
        if role_id is not None and self.bot._http is not None:
            await handle_reaction(self.bot, guild_id, user_id, role_id, added=False)

    @Cog.command()
    async def add(self, ctx: fluxer.Message):
        if ctx.guild_id is None:
            await ctx.reply("This command can only be used in a server.")
            return

        if not await is_admin(self.bot, ctx):
            await ctx.reply("You need administrator permissions to use this command.")
            return

        configured = get_configured_message(ctx.guild_id)
        if configured is None:
            await ctx.reply(
                "No role react message is configured. Use `!role setmessage <message_link>` first."
            )
            return

        role_match = re.search(r"<@&(\d+)>", ctx.content)
        if role_match is None:
            await ctx.reply("Please mention a role. Usage: `!role add @Role :emoji:`")
            return

        role_id = int(role_match.group(1))

        after_role = ctx.content[role_match.end() :].strip()
        if not after_role:
            await ctx.reply("Please provide an emoji. Usage: `!role add @Role :emoji:`")
            return

        cleaned = parse_emoji(after_role)

        if get_role_association(ctx.guild_id, cleaned) is not None:
            await ctx.reply(
                "That emoji is already associated with a role in this server."
            )
            return

        set_role_association(ctx.guild_id, role_id, cleaned)

        role_message = await self.bot.fetch_message(
            configured["channel_id"], configured["message_id"]
        )
        api_emoji = emoji_for_reaction_api(after_role)
        logger.info(f"Adding reaction, emoji: {api_emoji!r}")
        try:
            await role_message.add_reaction(api_emoji)
        except Exception as e:
            logger.error(f"Failed to add reaction: {e}")
            await ctx.reply(
                f"Associated {after_role.split()[0]} with <@&{role_id}>, but failed to add reaction to message."
            )
            return

        await ctx.reply(f"Associated {after_role.split()[0]} with <@&{role_id}>.")

    @Cog.command()
    async def remove(self, ctx: fluxer.Message):
        if ctx.guild_id is None:
            await ctx.reply("This command can only be used in a server.")
            return

        if not await is_admin(self.bot, ctx):
            await ctx.reply("You need administrator permissions to use this command.")
            return

        if get_configured_message(ctx.guild_id) is None:
            await ctx.reply(
                "No role react message is configured. Use `!role setmessage <message_link>` first."
            )
            return

        after_cmd = ctx.content.split("remove", 1)[-1].strip()
        if not after_cmd:
            await ctx.reply("Usage: `!role remove :emoji:`")
            return

        cleaned = parse_emoji(after_cmd)

        if not delete_role_association(ctx.guild_id, cleaned):
            await ctx.reply("That emoji is not associated with any role.")
            return

        await ctx.reply(f"Removed role association for {after_cmd.split()[0]}.")


async def setup(bot: fluxer.Bot):
    await bot.add_cog(ReactionHandling(bot))
