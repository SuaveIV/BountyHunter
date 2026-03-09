import logging
from typing import Any, cast

import discord
from discord.ext import commands

from bounty_core.epic import get_game_details as get_epic_details
from bounty_core.exceptions import AccessDenied, BountyException
from bounty_core.fetcher import TARGET_ACTOR
from bounty_core.gog import get_game_details as get_gog_details
from bounty_core.itch import get_game_details as get_itch_details
from bounty_core.parser import extract_game_title
from bounty_core.ps import get_game_details as get_ps_details
from bounty_core.steam import get_game_details as get_steam_details
from bounty_core.utils import enhance_details_with_itad, get_fallback_details

from .config import ADMIN_DISCORD_ID

logger = logging.getLogger(__name__)

SUPPORTS_SILENT = discord.version_info.major >= 2


def is_admin_dm():
    """Check if the command is invoked by the admin in a DM channel."""

    async def predicate(ctx):
        if not ADMIN_DISCORD_ID:
            return False
        if str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            return False
        if not isinstance(ctx.channel, discord.DMChannel):
            return False
        return True

    return commands.check(predicate)


async def send_message(target, content=None, embed=None, silent=False):
    """Helper to send messages with optional silent flag, compatible with older discord.py."""
    kwargs = {}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if silent:
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()
        if SUPPORTS_SILENT:
            kwargs["silent"] = True
    return await target.send(**kwargs)


async def create_game_embed(details: dict, parsed: dict) -> discord.Embed:
    """Creates a rich embed for a game announcement, matching FamilyBot style."""

    # BUG FIX: parsed.get("links", [""])[0] would raise IndexError if "links" key
    # exists but is an empty list. Use `or` to treat both missing and empty the same way.
    links = parsed.get("links") or [""]
    store_url = details.get("store_url") or links[0]

    # Determine store type
    is_steam = "store.steampowered.com" in store_url
    is_epic = "store.epicgames.com" in store_url
    is_itch = "itch.io" in store_url
    is_gog = "gog.com" in store_url
    is_ps = "store.playstation.com" in store_url
    is_amazon = "amazon.com" in store_url or "gaming.amazon.com" in store_url

    # Determine prefix based on parsed type
    post_type = parsed.get("type", "UNKNOWN")
    if post_type == "GAME":
        title_prefix = "FREE GAME"
    elif post_type == "ITEM":
        title_prefix = "FREE ITEM"
    else:
        title_prefix = "FREE"

    embed = discord.Embed()
    embed.title = f"{title_prefix}: {details.get('name', 'Unknown Game')}"
    embed.url = store_url or None

    # Footer keeps BountyHunter branding but dynamic TARGET_ACTOR
    embed.set_footer(text=f"BountyHunter • Free Game Scout • {TARGET_ACTOR}")

    if is_steam:
        embed.color = discord.Color.from_str("#00FF00")  # Green
        embed.description = details.get("short_description", parsed.get("text", "")) or "No description available."

        if details.get("image"):
            embed.set_image(url=details["image"])

        # Price Info
        price_info = details.get("price_info")
        if isinstance(price_info, dict):
            original = price_info.get("original_price", "N/A")
            discount = price_info.get("discount_percent", 0)
            embed.add_field(name="Price", value=f"~~{original}~~ -> FREE ({discount}% off)", inline=True)
        elif isinstance(price_info, str):
            embed.add_field(name="Price", value=price_info, inline=True)

        # Reviews
        if details.get("review_summary"):
            embed.add_field(name="Reviews", value=details["review_summary"], inline=True)

        # Release Date
        if details.get("release_date"):
            embed.add_field(name="Release Date", value=str(details["release_date"]), inline=True)

        # Creators
        developers = details.get("developers", [])
        publishers = details.get("publishers", [])
        if developers or publishers:
            dev_str = ", ".join(developers) if developers else "N/A"
            pub_str = ", ".join(publishers) if publishers else "N/A"
            embed.add_field(name="Creator(s)", value=f"**Dev:** {dev_str}\n**Pub:** {pub_str}", inline=True)

    elif is_epic:
        embed.color = discord.Color.from_str("#0078F2")  # Epic Blue
        embed.description = "Claim this game for free on the Epic Games Store!"
        embed.set_thumbnail(url="https://cdn.icon-icons.com/icons2/2699/PNG/128/epic_games_logo_icon_169084.png")
        embed.add_field(name="Platform", value="Epic Games Store", inline=True)
        if details.get("image"):
            embed.set_image(url=details["image"])

        # Add Mobile Links if detected
        mobile_links = parsed.get("epic_mobile_links", {})
        if mobile_links:
            links_str = " | ".join([f"[{k}]({v})" for k, v in mobile_links.items()])
            embed.add_field(name="📱 Mobile Versions", value=links_str, inline=False)

    elif is_itch:
        embed.color = discord.Color.from_str("#FA5C5C")  # Itch Pink
        embed.description = "Claim this game for free on Itch.io!"
        embed.set_thumbnail(url="https://cdn.icon-icons.com/icons2/2428/PNG/512/itch_io_logo_icon_147227.png")
        embed.add_field(name="Platform", value="Itch.io", inline=True)
        if details.get("image"):
            embed.set_image(url=details["image"])

    elif is_gog:
        embed.color = discord.Color.from_str("#8A4399")  # GOG Purple
        embed.description = "Claim this game for free on GOG.com!"
        embed.set_thumbnail(url="https://cdn.icon-icons.com/icons2/2428/PNG/512/gog_logo_icon_147232.png")
        embed.add_field(name="Platform", value="GOG.com", inline=True)
        if details.get("image"):
            embed.set_image(url=details["image"])

    elif is_amazon:
        embed.color = discord.Color.from_str("#00A8E1")  # Amazon Blue
        embed.description = "Claim this game for free with Amazon Prime Gaming!"
        embed.set_thumbnail(
            url="https://cdn.icon-icons.com/icons2/2699/PNG/128/amazon_prime_gaming_logo_icon_169083.png"
        )
        embed.add_field(name="Platform", value="Amazon Prime Gaming", inline=True)
        if details.get("image"):
            embed.set_image(url=details["image"])

    elif is_ps:
        embed.color = discord.Color.blue()
        embed.description = "Claim this game for free on the PlayStation Store!"
        embed.add_field(name="Platform", value="PlayStation Store", inline=True)
        if details.get("image"):
            embed.set_image(url=details["image"])

    else:
        # Fallback for generic sites
        embed.color = discord.Color.green()
        embed.description = details.get("description") or parsed.get("text", "Free game announcement")
        if details.get("image"):
            embed.set_image(url=details["image"])

    # Retain original link logic for "Additional Links" and "Sources"
    def normalize_url(url: str) -> str:
        if not url:
            return ""
        return url.split("?")[0].split("#")[0].rstrip("/").lower()

    exclude_urls = {normalize_url(store_url)}
    source_set = set(parsed.get("source_links", []))
    for source in source_set:
        exclude_urls.add(normalize_url(source))

    other_links = []
    seen_normalized = set()
    for link in parsed.get("links", []):
        norm_link = normalize_url(link)
        if norm_link in exclude_urls or norm_link in seen_normalized:
            continue
        seen_normalized.add(norm_link)
        other_links.append(link)

    if other_links:
        links_text = "\n".join([f"• [Link {i + 1}]({link})" for i, link in enumerate(other_links[:5])])
        if len(other_links) > 5:
            links_text += f"\n*...and {len(other_links) - 5} more*"
        if len(links_text) <= 1024:
            embed.add_field(name="🔗 Additional Links", value=links_text, inline=False)

    if source_set:
        sources = list(source_set)
        sources_text = "\n".join([f"• [Source {i + 1}]({link})" for i, link in enumerate(sources[:3])])
        if len(sources) > 3:
            sources_text += f"\n*...and {len(sources) - 3} more*"
        if len(sources_text) <= 1024:
            embed.add_field(name="📰 Sources", value=sources_text, inline=False)

    return embed


async def create_fallback_message(parsed: dict, role_id: int | None) -> str:
    text = parsed.get("text", "")
    links = parsed.get("links", [])
    source_links = parsed.get("source_links", [])
    content = text
    all_links = links + source_links
    for link in all_links:
        if link not in content:
            content += f"\n{link}"
    if role_id:
        content = f"<@&{role_id}>\n{content}"
    return content


async def resolve_game_details(bot: commands.Bot, parsed: dict[str, Any]) -> dict[str, Any] | None:
    """
    Central logic to resolve game details from a parsed post using available bot managers.

    Refactored to attempt all available store IDs in the parsed dict, collect all results,
    and return the best one based on completeness (has image, has description, etc.).
    """
    # Cast to Any to access dynamic attributes (managers) without strict Gunship dependency
    bot_any = cast(Any, bot)

    steam_ids = parsed.get("steam_app_ids", [])
    epic_slugs = parsed.get("epic_slugs", [])
    itch_urls = parsed.get("itch_urls", [])
    ps_urls = parsed.get("ps_urls", [])
    gog_urls = parsed.get("gog_urls", [])

    # Collect results from all available stores
    all_results = []

    # Try Steam
    if steam_ids and getattr(bot_any, "steam_manager", None):
        for steam_id in steam_ids:
            try:
                result = await get_steam_details(steam_id, bot_any.steam_manager, bot_any.store)
                if result:
                    all_results.append(result)
            except AccessDenied as e:
                logger.warning(
                    f"Access denied (Steam) for item '{parsed.get('text')}': {e}. Continuing with other stores."
                )
            except BountyException as e:
                logger.warning(
                    f"Error resolving Steam details ({type(e).__name__}): {e}. Continuing with other stores."
                )
            except Exception as e:
                logger.exception(f"Unexpected error in Steam resolve_game_details: {e}. Continuing with other stores.")

    # Try Epic
    if epic_slugs and getattr(bot_any, "epic_manager", None):
        for epic_slug in epic_slugs:
            try:
                result = await get_epic_details(epic_slug, bot_any.epic_manager, bot_any.store)
                if result:
                    all_results.append(result)
            except AccessDenied as e:
                logger.warning(
                    f"Access denied (Epic) for item '{parsed.get('text')}': {e}. Continuing with other stores."
                )
            except BountyException as e:
                logger.warning(f"Error resolving Epic details ({type(e).__name__}): {e}. Continuing with other stores.")
            except Exception as e:
                logger.exception(f"Unexpected error in Epic resolve_game_details: {e}. Continuing with other stores.")

    # Try Itch
    if itch_urls and getattr(bot_any, "itch_manager", None):
        for itch_url in itch_urls:
            try:
                result = await get_itch_details(itch_url, bot_any.itch_manager, bot_any.store)
                if result:
                    all_results.append(result)
            except AccessDenied as e:
                logger.warning(
                    f"Access denied (Itch) for item '{parsed.get('text')}': {e}. Continuing with other stores."
                )
            except BountyException as e:
                logger.warning(f"Error resolving Itch details ({type(e).__name__}): {e}. Continuing with other stores.")
            except Exception as e:
                logger.exception(f"Unexpected error in Itch resolve_game_details: {e}. Continuing with other stores.")

    # Try PlayStation
    if ps_urls and getattr(bot_any, "ps_manager", None):
        for ps_url in ps_urls:
            try:
                result = await get_ps_details(ps_url, bot_any.ps_manager, bot_any.store)
                if result:
                    all_results.append(result)
            except AccessDenied as e:
                logger.warning(
                    f"Access denied (PlayStation) for item '{parsed.get('text')}': {e}. Continuing with other stores."
                )
            except BountyException as e:
                logger.warning(
                    f"Error resolving PlayStation details ({type(e).__name__}): {e}. Continuing with other stores."
                )
            except Exception as e:
                logger.exception(
                    f"Unexpected error in PlayStation resolve_game_details: {e}. Continuing with other stores."
                )

    # Try GOG
    if gog_urls and getattr(bot_any, "gog_manager", None):
        for gog_url in gog_urls:
            try:
                result = await get_gog_details(gog_url, bot_any.gog_manager, bot_any.store)
                if result:
                    all_results.append(result)
            except AccessDenied as e:
                logger.warning(
                    f"Access denied (GOG) for item '{parsed.get('text')}': {e}. Continuing with other stores."
                )
            except BountyException as e:
                logger.warning(f"Error resolving GOG details ({type(e).__name__}): {e}. Continuing with other stores.")
            except Exception as e:
                logger.exception(f"Unexpected error in GOG resolve_game_details: {e}. Continuing with other stores.")

    # Select the best result based on completeness
    details = select_best_game_details(all_results)

    # Universal Fallback: Use ITAD if no store succeeded
    if not details and getattr(bot_any, "itad_manager", None):
        raw_text = parsed.get("text", "")
        # BUG FIX: Pass a clean game title to ITAD rather than the raw Reddit post text.
        # e.g. "[Steam] (Game) Portal is free!" → "Portal"
        # Passing the raw string would produce garbage ITAD matches. Only fall back to
        # the raw text if the regex can't extract a structured title (e.g. Amazon posts).
        itad_title = extract_game_title(raw_text) or raw_text or None
        details = await bot_any.itad_manager.find_game(
            steam_ids=list(steam_ids) if steam_ids else None,
            epic_slugs=list(epic_slugs) if epic_slugs else None,
            title=itad_title,
        )

    # Fallback: use generic details if specific manager didn't handle it
    if not details and parsed.get("links"):
        details = await get_fallback_details(
            parsed["links"], parsed["text"], getattr(bot_any, "itad_manager", None), image=parsed.get("image")
        )

    return details


def select_best_game_details(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Selects the best game details from a list of results based on completeness.

    Scoring criteria (in order of importance):
    1. Has an image (most important for Discord embeds)
    2. Has a description/short_description
    3. Has price information
    4. Has developer/publisher information
    5. Has release date
    6. Has a valid name

    Returns the result with the highest score, or None if no results.
    """
    if not results:
        return None

    def calculate_score(result: dict[str, Any]) -> int:
        score = 0

        # Has image (most important for Discord embeds)
        if result.get("image"):
            score += 100

        # Has description
        if result.get("short_description") or result.get("description"):
            score += 50

        # Has price information
        if result.get("price_info"):
            score += 25

        # Has developer/publisher information
        if result.get("developers") or result.get("publishers"):
            score += 20

        # Has release date
        if result.get("release_date"):
            score += 10

        # Has a valid name
        if result.get("name") and result["name"] != "Free Game":
            score += 5

        return score

    # Sort by score (highest first) and return the best
    best_result = max(results, key=calculate_score)
    return best_result


# Explicitly re-export for consumers of this module
__all__ = [
    "is_admin_dm",
    "send_message",
    "create_game_embed",
    "create_fallback_message",
    "enhance_details_with_itad",
    "get_fallback_details",
    "resolve_game_details",
]
