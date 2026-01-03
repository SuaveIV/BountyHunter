import discord
from discord.ext import commands

from ..logging_config import get_logger
from ..utils import send_message

logger = get_logger(__name__)


class Beacons(commands.Cog):
    """
    Beacons Cog: Manages channel subscriptions (signal beacons).
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="subscribe")
    @commands.has_permissions(manage_guild=True)
    async def subscribe_command(self, ctx: commands.Context, role: discord.Role | None = None):
        """Subscribe the current channel to free game announcements (Guild only)."""
        try:
            if not ctx.guild:
                await ctx.send("Subscription only works within a guild.")
                return

            role_id = role.id if role else None
            await self.bot.store.add_subscription(ctx.guild.id, ctx.channel.id, role_id)

            msg = "This channel is subscribed to free-game announcements."
            if role:
                msg += f" I will ping {role.mention}."
            await send_message(ctx, msg, silent=True)
        except Exception as e:
            logger.exception("subscribe failed: %s", e)
            await send_message(ctx, "Failed to subscribe. See logs.", silent=True)

    @subscribe_command.error
    async def subscribe_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_message(ctx, "You need Manage Guild permission to run this.", silent=True)

    @commands.command(name="unsubscribe")
    @commands.has_permissions(manage_guild=True)
    async def unsubscribe_command(self, ctx: commands.Context):
        """Unsubscribe the current channel from free game announcements (Guild only)."""
        try:
            if not ctx.guild:
                await ctx.send("Unsubscribe only works within a guild.")
                return
            await self.bot.store.remove_subscription(ctx.guild.id, ctx.channel.id)
            await send_message(ctx, "This channel has been unsubscribed.", silent=True)
        except Exception as e:
            logger.exception("unsubscribe failed: %s", e)
            await send_message(ctx, "Failed to unsubscribe. See logs.", silent=True)

    @unsubscribe_command.error
    async def unsubscribe_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_message(ctx, "You need Manage Guild permission to run this.", silent=True)


async def setup(bot):
    await bot.add_cog(Beacons(bot))
