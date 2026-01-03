import logging

import discord
from discord.ext import commands

from bounty_core.fetcher import TARGET_ACTOR
from bounty_core.parser import extract_game_title

from .config import ADMIN_DISCORD_ID, ITAD_API_KEY

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
    store_url = details.get("store_url", parsed.get("links", [""])[0])

    # Determine store type
    is_steam = "store.steampowered.com" in store_url
    is_epic = "store.epicgames.com" in store_url
    is_itch = "itch.io" in store_url
    is_gog = "gog.com" in store_url
    is_ps = "store.playstation.com" in store_url
    is_amazon = "amazon.com" in store_url or "gaming.amazon.com" in store_url
    is_stove = "stove.com" in store_url or "onstove.com" in store_url

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
    embed.url = store_url

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

    elif is_stove:
        embed.color = discord.Color.from_str("#FF6B00")  # STOVE Orange
        embed.description = "Claim this game for free on STOVE!"
        embed.add_field(name="Platform", value="STOVE", inline=True)
        if details.get("image"):
            embed.set_image(url=details["image"])

    else:
        # Fallback for generic sites
        embed.color = discord.Color.green()
        # If description is not provided in details, use text
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


async def get_fallback_details(links: list[str], text: str, itad_manager, image: str | None = None) -> dict:
    """
    Generate basic details from links/text when no specific API manager is available.
    Optionally attempts to fetch missing image from ITAD.
    """
    fallback_url = None
    for link in links:
        if any(d in link for d in ["gog.com", "amazon.com", "onstove.com", "stove.com"]):
            fallback_url = link
            break
    if not fallback_url and links:
        fallback_url = links[0]

    if not fallback_url:
        return {}

    title = extract_game_title(text) or "Free Game"

    # Heuristic: if title wasn't extracted and text is short, assume text is the title
    if title == "Free Game" and text and len(text) < 50 and "http" not in text:
        title = text

    details = {
        "name": title,
        "store_url": fallback_url,
        "image": image,
    }

    # Use the shared enhancement function to try getting an image if missing
    if not details["image"] and itad_manager:
        await enhance_details_with_itad(details, itad_manager)

    return details


async def enhance_details_with_itad(details: dict, itad_manager) -> None:
    """
    Attempts to fetch missing metadata (currently just image) from ITAD
    for any given details dictionary. Modifies details in-place.
    """
    if not ITAD_API_KEY:
        return

    title = details.get("name")
    if not title or title == "Free Game":
        return

    # If image is missing, try to find it
    if not details.get("image"):
        try:
            results = await itad_manager.search_game(title, limit=1)
            if results:
                game_info = results[0]
                assets = game_info.get("assets", {})
                banner = assets.get("banner400") or assets.get("banner300") or assets.get("boxArt")
                if banner:
                    details["image"] = banner
                    logger.info(f"Fetched image for '{title}' from ITAD")
        except Exception as e:
            logger.warning(f"Failed to fetch ITAD image for '{title}': {e}")
