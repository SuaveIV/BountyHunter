from bounty_core.parser import determine_content_type, extract_steam_ids, is_safe_link


def test_extract_steam_ids_found():
    text = "Check out https://store.steampowered.com/app/12345/Game_Name and store.steampowered.com/app/67890"
    ids = extract_steam_ids(text)
    assert ids == {"12345", "67890"}


def test_extract_steam_ids_none():
    text = "No steam links here https://google.com"
    ids = extract_steam_ids(text)
    assert ids == set()


def test_is_safe_link():
    assert is_safe_link("https://store.steampowered.com")
    assert not is_safe_link("https://givee.club/raffle")
    assert not is_safe_link("https://gleam.io/contest")


def test_determine_content_type():
    assert determine_content_type("[Steam] (Game) Some Game") == "GAME"
    assert determine_content_type("[Epic] (Game) Another Game") == "GAME"
    assert determine_content_type("[Steam] (DLC) Some DLC") == "ITEM"
    assert determine_content_type("[Ubisoft] (Beta) Skull and Bones") == "ITEM"
    assert determine_content_type("[PSA] Info Post") == "INFO"
    assert determine_content_type("Random Title") == "UNKNOWN"


def test_is_safe_link_stove():
    assert not is_safe_link("https://stove.com/game")
    assert not is_safe_link("https://store.onstove.com/game")
