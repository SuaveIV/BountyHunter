import importlib.util

import pytest


async def test_integration_setup():
    """
    A basic smoke test to verify that the integration folder is discovered
    and that the source code is accessible via pythonpath.
    """
    if importlib.util.find_spec("bounty_discord") is None:
        pytest.fail("Failed to import bounty_discord")

    assert True
