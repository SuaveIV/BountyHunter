from bs4 import BeautifulSoup

from bounty_core.parser import (
    extract_epic_slugs,
    extract_game_title,
    extract_gog_urls,
    extract_itch_urls,
    extract_og_data,
    extract_ps_urls,
)


def test_extract_game_title():
    # FGF Title Regex: [Platform] (Game) Title is free
    assert extract_game_title("[Steam] (Game) Portal is free") == "Portal"
    assert extract_game_title("[Epic] (Game) Fortnite is free today") == "Fortnite"

    # FGF PSA Regex: [PSA] Title is complimentary
    assert extract_game_title("[PSA] Fallout 76 is complimentary") == "Fallout 76"

    # Fallback
    assert extract_game_title("Random Text") is None


def test_extract_epic_slugs():
    text = "Get it here: https://store.epicgames.com/en-US/p/fortnite and https://store.epicgames.com/p/rocket-league"
    slugs = extract_epic_slugs(text)
    assert slugs == {"fortnite", "rocket-league"}


def test_extract_itch_urls():
    text = "Indie game: https://tobyfox.itch.io/deltarune check it out"
    urls = extract_itch_urls(text)
    assert urls == {"https://tobyfox.itch.io/deltarune"}


def test_extract_ps_urls():
    text = "Sony deal: https://store.playstation.com/en-us/product/UP9000-CUSA00917_00-THELASTOFUS00000"
    urls = extract_ps_urls(text)
    # The regex captures the full URL in group 1
    assert urls == {"https://store.playstation.com/en-us/product/UP9000-CUSA00917_00-THELASTOFUS00000"}


def test_extract_gog_urls():
    text = "GOG freebie: https://www.gog.com/game/cyberpunk_2077 and https://gog.com/en/game/witcher_3"
    urls = extract_gog_urls(text)
    assert urls == {
        "https://www.gog.com/game/cyberpunk_2077",
        "https://gog.com/en/game/witcher_3",
    }


def test_extract_og_data_standard():
    html = """
    <html>
        <head>
            <meta property="og:title" content="The Game" />
            <meta property="og:image" content="http://example.com/image.jpg" />
        </head>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    data = extract_og_data(soup)
    assert data["title"] == "The Game"
    assert data["image"] == "http://example.com/image.jpg"


def test_extract_og_data_missing():
    html = "<html><head></head></html>"
    soup = BeautifulSoup(html, "html.parser")
    data = extract_og_data(soup)
    assert data["title"] is None
    assert data["image"] is None
