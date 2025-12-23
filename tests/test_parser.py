from bounty_core.parser import extract_links, extract_steam_ids, is_safe_link


def test_extract_steam_ids_found():
    text = "Check out https://store.steampowered.com/app/12345/Game_Name and store.steampowered.com/app/67890"
    ids = extract_steam_ids(text)
    assert ids == {"12345", "67890"}


def test_extract_steam_ids_none():
    text = "No steam links here https://google.com"
    ids = extract_steam_ids(text)
    assert ids == set()


def test_extract_links_facets():
    post = {
        "record": {
            "text": "Link here",
            "facets": [{"features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://facet.com"}]}],
        }
    }
    assert "https://facet.com" in extract_links(post)


def test_extract_links_text_fallback():
    post = {"record": {"text": "Raw link: https://text.com/foo"}}
    assert "https://text.com/foo" in extract_links(post)


def test_extract_links_embed():
    post = {
        "embed": {
            "$type": "app.bsky.embed.external#view",
            "external": {"uri": "https://embed.com"},
        }
    }
    assert "https://embed.com" in extract_links(post)


def test_is_safe_link():
    assert is_safe_link("https://store.steampowered.com")
    assert not is_safe_link("https://givee.club/raffle")
    assert not is_safe_link("https://gleam.io/contest")
