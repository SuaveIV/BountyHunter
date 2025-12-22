from typing import List, Dict
import re
from urllib.parse import urlparse

STEAM_RE = re.compile(r"store\.steampowered\.com\/app\/(\d+)", re.IGNORECASE)


def parse_post_for_links(post: Dict) -> Dict:
    """
    Parse a normalized post dict (uri, text) into extracted result:
    {
      "uri": "...",
      "text": "...",
      "links": ["https://..."],
      "steam_app_ids": ["12345"]
    }
    """
    text = post.get("text", "")
    # Basic URL extraction (reuse fetcher.extract_links_from_text at higher level)
    # For simplicity, assume links already found upstream; if not, naive find here:
    links = []
    # naive URL regex
    import re

    URL_RE = re.compile(r"https?://[^\s)>\]]+")
    links = URL_RE.findall(text)

    steam_ids = []
    for link in links:
        m = STEAM_RE.search(link)
        if m:
            steam_ids.append(m.group(1))

    return {"uri": post.get("uri"), "text": text, "links": links, "steam_app_ids": steam_ids}