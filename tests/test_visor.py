from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bounty_discord.cogs.visor import SectorVisor, _retry_send_message


class TestRetrySendMessage:
    """Test the _retry_send_message helper function."""

    @pytest.mark.asyncio
    async def test_retry_send_message_success(self):
        """Test that _retry_send_message works on first attempt."""
        mock_channel = AsyncMock()
        mock_message = MagicMock()

        with patch("bounty_discord.cogs.visor.send_message", return_value=mock_message) as mock_send_message:
            result = await _retry_send_message(mock_channel, content="test", max_retries=3)

            assert result == mock_message
            mock_send_message.assert_called_once_with(mock_channel, content="test", embed=None, silent=False)

    @pytest.mark.asyncio
    async def test_retry_send_message_retries_transient_errors(self):
        """Test that _retry_send_message retries on transient HTTP errors."""
        mock_channel = AsyncMock()
        mock_message = MagicMock()

        # First two calls raise transient errors, third succeeds
        mock_channel.send.side_effect = [
            discord.HTTPException(MagicMock(status=429), "Rate limited"),
            discord.HTTPException(MagicMock(status=500), "Internal error"),
            mock_message,
        ]

        # BUG FIX: patch must target the module where asyncio.sleep is called,
        # not the top-level asyncio module, otherwise the real sleep runs in tests.
        with patch("bounty_discord.cogs.visor.asyncio.sleep") as mock_sleep:
            result = await _retry_send_message(mock_channel, content="test", max_retries=3)

        assert result == mock_message
        assert mock_channel.send.call_count == 3
        # Verify exponential backoff delays: 2^0=1, 2^1=2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    @pytest.mark.asyncio
    async def test_retry_send_message_re_raises_non_retryable_errors(self):
        """Test that _retry_send_message re-raises non-retryable errors immediately."""
        mock_channel = AsyncMock()

        # 403 Forbidden is not retryable
        error = discord.HTTPException(MagicMock(status=403), "Forbidden")

        with patch("bounty_discord.cogs.visor.send_message", side_effect=error) as mock_send_message:
            with pytest.raises(discord.HTTPException) as exc_info:
                await _retry_send_message(mock_channel, content="test", max_retries=3)

            assert exc_info.value == error
            # Should have given up immediately with no retries
            mock_send_message.assert_called_once_with(mock_channel, content="test", embed=None, silent=False)

    @pytest.mark.asyncio
    async def test_retry_send_message_exhausts_retries(self):
        """Test that _retry_send_message raises after exhausting retries."""
        mock_channel = AsyncMock()

        # Always raise transient error
        mock_channel.send.side_effect = discord.HTTPException(MagicMock(status=503), "Service unavailable")

        with patch("bounty_discord.cogs.visor.asyncio.sleep") as mock_sleep:
            with pytest.raises(discord.HTTPException):
                await _retry_send_message(mock_channel, content="test", max_retries=2)

        assert mock_channel.send.call_count == 2
        mock_sleep.assert_called_once_with(1)  # One delay (2^0) before the second attempt, then gives up


class TestSectorVisorAnnounceNew:
    """Test the SectorVisor._announce_new method."""

    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot with required attributes."""
        bot = MagicMock()
        bot.store = AsyncMock()
        bot.itad_manager = AsyncMock()
        return bot

    @pytest.fixture
    def mock_visor(self, mock_bot):
        """Create a SectorVisor instance with mocked dependencies."""
        # Create visor without starting the scheduled task
        visor = SectorVisor.__new__(SectorVisor)
        visor.bot = mock_bot
        # Mock the scheduled task to avoid event loop issues
        visor.scheduled_check = MagicMock()
        return visor

    @pytest.fixture
    def mock_messageable_channel(self):
        """Create a mock channel that is messageable."""
        mock_channel = AsyncMock()
        mock_channel.__class__ = type("MessageableChannel", (mock_channel.__class__, discord.abc.Messageable), {})
        return mock_channel

    @pytest.fixture
    def sample_items(self):
        """Sample parsed items for testing."""
        return [
            (
                "test-uri-1",
                {
                    "text": "Free game: Test Game",
                    "links": ["https://store.steampowered.com/app/123456"],
                    "type": "GAME",
                    "steam_app_ids": ["123456"],
                },
            ),
            (
                "test-uri-2",
                {
                    "text": "Free item: Test Item",
                    "links": ["https://example.com/item"],
                    "type": "ITEM",
                    "steam_app_ids": [],
                },
            ),
        ]

    @pytest.fixture
    def sample_subscriptions(self):
        """Sample subscription data."""
        return [
            (123456789, 987654321, 555666777),  # Guild, Channel, Role
            (111222333, 444555666, None),  # Guild, Channel, No Role
        ]

    @pytest.mark.asyncio
    async def test_announce_new_with_subscriptions_and_details(
        self, mock_visor, sample_items, sample_subscriptions, mock_messageable_channel
    ):
        """Test that posts are sent to all subscribed channels when details are resolved."""
        mock_visor.bot.store.get_subscriptions.return_value = sample_subscriptions
        mock_visor.bot.get_channel.return_value = mock_messageable_channel

        mock_details = {
            "name": "Test Game",
            "short_description": "A test game",
            "image": "https://example.com/image.jpg",
            "price_info": {"original_price": "$9.99", "discount_percent": 100},
        }
        mock_visor.bot.itad_manager.find_game.return_value = None

        with (
            patch("bounty_discord.cogs.visor.resolve_game_details", return_value=mock_details),
            patch("bounty_discord.cogs.visor.create_game_embed") as mock_create_embed,
            patch("bounty_discord.cogs.visor._retry_send_message") as mock_send,
        ):
            mock_embed = MagicMock()
            mock_create_embed.return_value = mock_embed

            await mock_visor._announce_new(sample_items)

            mock_visor.bot.store.get_subscriptions.assert_called_once()

            # 2 items × 2 channels = 4 sends
            assert mock_send.call_count == 4

            # Post marked seen after announcement, once per item
            assert mock_visor.bot.store.mark_post_seen.call_count == 2
            mock_visor.bot.store.mark_post_seen.assert_any_call("test-uri-1")
            mock_visor.bot.store.mark_post_seen.assert_any_call("test-uri-2")

    @pytest.mark.asyncio
    async def test_announce_new_with_fallback_messages(self, mock_visor, sample_items, sample_subscriptions):
        """Test that fallback messages are used when details cannot be resolved."""
        mock_visor.bot.store.get_subscriptions.return_value = sample_subscriptions

        mock_messageable_channel = AsyncMock()
        mock_messageable_channel.__class__ = type(
            "MessageableChannel", (mock_messageable_channel.__class__, discord.abc.Messageable), {}
        )
        mock_visor.bot.get_channel.return_value = mock_messageable_channel

        with (
            patch("bounty_discord.cogs.visor.resolve_game_details", return_value=None),
            patch("bounty_discord.cogs.visor.create_fallback_message") as mock_create_fallback,
            patch("bounty_discord.cogs.visor._retry_send_message") as mock_send,
        ):
            mock_fallback_message = "Free game: Test Game\nhttps://store.steampowered.com/app/123456"
            mock_create_fallback.return_value = mock_fallback_message

            await mock_visor._announce_new(sample_items)

            # create_fallback_message is called inside the channel loop, so once per item × channel
            assert mock_create_fallback.call_count == 4  # 2 items × 2 channels
            assert mock_send.call_count == 4

            assert mock_visor.bot.store.mark_post_seen.call_count == 2

    @pytest.mark.asyncio
    async def test_announce_new_with_http_exception_handling(
        self, mock_visor, sample_items, sample_subscriptions, mock_messageable_channel
    ):
        """Test that HTTP exceptions in one channel don't prevent other channels from receiving announcements."""
        mock_visor.bot.store.get_subscriptions.return_value = sample_subscriptions
        mock_visor.bot.get_channel.return_value = mock_messageable_channel

        mock_details = {
            "name": "Test Game",
            "short_description": "A test game",
            "image": "https://example.com/image.jpg",
        }
        mock_visor.bot.itad_manager.find_game.return_value = None

        with (
            patch("bounty_discord.cogs.visor.resolve_game_details", return_value=mock_details),
            patch("bounty_discord.cogs.visor.create_game_embed"),
            patch("bounty_discord.cogs.visor._retry_send_message") as mock_send,
        ):
            # First channel fails after retries exhausted, rest succeed
            mock_send.side_effect = [
                discord.HTTPException(MagicMock(status=500), "Server error"),
                None,
                None,
                None,
            ]

            await mock_visor._announce_new(sample_items)

            # All 4 sends were attempted despite the first failure
            assert mock_send.call_count == 4

            # Post marked seen for both items regardless of partial send failure
            assert mock_visor.bot.store.mark_post_seen.call_count == 2

    @pytest.mark.asyncio
    async def test_announce_new_with_no_subscriptions(self, mock_visor, sample_items):
        """Test that nothing is sent and nothing is marked seen when there are no subscriptions."""
        mock_visor.bot.store.get_subscriptions.return_value = []

        with (
            patch("bounty_discord.cogs.visor.resolve_game_details") as mock_resolve,
            patch("bounty_discord.cogs.visor._retry_send_message") as mock_send,
        ):
            await mock_visor._announce_new(sample_items)

            mock_visor.bot.store.get_subscriptions.assert_called_once()

            # The early return on empty subs is BEFORE the item loop, so resolve is never called.
            mock_resolve.assert_not_awaited()

            # No messages sent and nothing marked seen
            mock_send.assert_not_called()
            mock_visor.bot.store.mark_post_seen.assert_not_called()

    @pytest.mark.asyncio
    async def test_announce_new_with_empty_items(self, mock_visor):
        """Test that nothing happens when no items are provided."""
        with (
            patch("bounty_discord.cogs.visor.resolve_game_details") as mock_resolve,
            patch("bounty_discord.cogs.visor._retry_send_message") as mock_send,
        ):
            await mock_visor._announce_new([])

            mock_visor.bot.store.get_subscriptions.assert_not_called()
            mock_resolve.assert_not_awaited()
            mock_send.assert_not_called()
            mock_visor.bot.store.mark_post_seen.assert_not_called()

    @pytest.mark.asyncio
    async def test_announce_new_with_itad_enhancement(
        self, mock_visor, sample_items, sample_subscriptions, mock_messageable_channel
    ):
        """Test that ITAD enhancement is applied when details are resolved."""
        mock_visor.bot.store.get_subscriptions.return_value = sample_subscriptions
        mock_visor.bot.get_channel.return_value = mock_messageable_channel

        mock_details = {"name": "Test Game", "short_description": "A test game"}
        mock_visor.bot.itad_manager.find_game.return_value = None

        with (
            patch("bounty_discord.cogs.visor.resolve_game_details", return_value=mock_details),
            patch("bounty_discord.cogs.visor.enhance_details_with_itad") as mock_enhance,
            patch("bounty_discord.cogs.visor.create_game_embed") as mock_create_embed,
            patch("bounty_discord.cogs.visor._retry_send_message"),
        ):
            mock_embed = MagicMock()
            mock_create_embed.return_value = mock_embed

            await mock_visor._announce_new(sample_items)

            # ITAD enhancement called once per item, not once per channel
            assert mock_enhance.call_count == 2
            mock_enhance.assert_any_call(mock_details, mock_visor.bot.itad_manager)

    @pytest.mark.asyncio
    async def test_announce_new_with_unknown_game_name(self, mock_visor, sample_items, sample_subscriptions):
        """Test that fallback messages are used when game name contains 'Unknown'."""
        mock_visor.bot.store.get_subscriptions.return_value = sample_subscriptions

        mock_messageable_channel = AsyncMock()
        mock_messageable_channel.__class__ = type(
            "MessageableChannel", (mock_messageable_channel.__class__, discord.abc.Messageable), {}
        )
        mock_visor.bot.get_channel.return_value = mock_messageable_channel

        mock_details = {"name": "Unknown Game", "short_description": "A test game"}
        mock_visor.bot.itad_manager.find_game.return_value = None

        with (
            patch("bounty_discord.cogs.visor.resolve_game_details", return_value=mock_details),
            patch("bounty_discord.cogs.visor.create_fallback_message") as mock_create_fallback,
            patch("bounty_discord.cogs.visor._retry_send_message") as mock_send,
        ):
            mock_fallback_message = "Free game: Test Game\nhttps://store.steampowered.com/app/123456"
            mock_create_fallback.return_value = mock_fallback_message

            await mock_visor._announce_new(sample_items)

            # create_fallback_message is called inside the channel loop, once per item × channel
            assert mock_create_fallback.call_count == 4  # 2 items × 2 channels
            assert mock_send.call_count == 4

    @pytest.mark.asyncio
    async def test_announce_new_with_role_mentions(
        self, mock_visor, sample_items, sample_subscriptions, mock_messageable_channel
    ):
        """Test that role mentions are included when role_id is present."""
        mock_visor.bot.store.get_subscriptions.return_value = sample_subscriptions
        mock_visor.bot.get_channel.return_value = mock_messageable_channel

        mock_details = {
            "name": "Test Game",
            "short_description": "A test game",
            "image": "https://example.com/image.jpg",
        }
        mock_visor.bot.itad_manager.find_game.return_value = None

        with (
            patch("bounty_discord.cogs.visor.resolve_game_details", return_value=mock_details),
            patch("bounty_discord.cogs.visor.create_game_embed") as mock_create_embed,
            patch("bounty_discord.cogs.visor._retry_send_message") as mock_send,
        ):
            mock_embed = MagicMock()
            mock_create_embed.return_value = mock_embed

            await mock_visor._announce_new(sample_items)

            assert mock_send.call_count == 4

            # Sends are ordered: item1/channel1, item1/channel2, item2/channel1, item2/channel2
            call_args_list = mock_send.call_args_list
            assert call_args_list[0][1]["content"] == "<@&555666777>"  # channel 1 has role
            assert call_args_list[1][1]["content"] is None             # channel 2 has no role
            assert call_args_list[2][1]["content"] == "<@&555666777>"  # channel 1 has role
            assert call_args_list[3][1]["content"] is None             # channel 2 has no role

    @pytest.mark.asyncio
    async def test_announce_new_with_channel_fetching(
        self, mock_visor, sample_items, sample_subscriptions, mock_messageable_channel
    ):
        """Test that channels are fetched via fetch_channel when not found in the local cache."""
        mock_visor.bot.store.get_subscriptions.return_value = sample_subscriptions

        mock_details = {
            "name": "Test Game",
            "short_description": "A test game",
            "image": "https://example.com/image.jpg",
        }
        mock_visor.bot.itad_manager.find_game.return_value = None

        # get_channel returns None for all lookups (nothing in cache)
        # BUG FIX: original test only had 2 Nones for 4 lookups (2 items × 2 subs),
        # causing StopIteration on the 3rd call. Need one None per lookup.
        mock_channel1 = AsyncMock()
        mock_channel2 = AsyncMock()
        mock_channel1.__class__ = type("MC", (mock_channel1.__class__, discord.abc.Messageable), {})
        mock_channel2.__class__ = type("MC", (mock_channel2.__class__, discord.abc.Messageable), {})

        mock_visor.bot.get_channel.return_value = None  # Always miss cache
        # fetch_channel is awaited in visor.py, so it must be an AsyncMock.
        # plain MagicMock (the default on a MagicMock bot) is not awaitable.
        mock_visor.bot.fetch_channel = AsyncMock(side_effect=[
            mock_channel1, mock_channel2,  # item 1: fetch both channels
            mock_channel1, mock_channel2,  # item 2: fetch again (no local caching in visor)
        ])

        with (
            patch("bounty_discord.cogs.visor.resolve_game_details", return_value=mock_details),
            patch("bounty_discord.cogs.visor.create_game_embed") as mock_create_embed,
            patch("bounty_discord.cogs.visor._retry_send_message") as mock_send,
        ):
            mock_embed = MagicMock()
            mock_create_embed.return_value = mock_embed

            await mock_visor._announce_new(sample_items)

            # get_channel called for every item × subscription combination
            assert mock_visor.bot.get_channel.call_count == 4
            # fetch_channel called for every miss (all 4, since cache always misses)
            assert mock_visor.bot.fetch_channel.call_count == 4
            assert mock_send.call_count == 4

    @pytest.mark.asyncio
    async def test_announce_new_with_non_messageable_channel(
        self, mock_visor, sample_items, sample_subscriptions, mock_messageable_channel
    ):
        """Test that non-messageable channels are skipped."""
        mock_visor.bot.store.get_subscriptions.return_value = sample_subscriptions

        mock_details = {
            "name": "Test Game",
            "short_description": "A test game",
            "image": "https://example.com/image.jpg",
        }
        mock_visor.bot.itad_manager.find_game.return_value = None

        # In discord.py 2.x VoiceChannel IS Messageable (stage/voice text support was added).
        # CategoryChannel is not Messageable and works correctly for this test.
        mock_non_messageable_channel = MagicMock(spec=discord.CategoryChannel)
        mock_visor.bot.get_channel.return_value = mock_non_messageable_channel

        with (
            patch("bounty_discord.cogs.visor.resolve_game_details", return_value=mock_details),
            patch("bounty_discord.cogs.visor.create_game_embed"),
            patch("bounty_discord.cogs.visor._retry_send_message") as mock_send,
        ):
            await mock_visor._announce_new(sample_items)

            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_announce_new_with_exception_during_send(
        self, mock_visor, sample_items, sample_subscriptions, mock_messageable_channel
    ):
        """Test that exceptions during send are logged but don't stop processing."""
        mock_visor.bot.store.get_subscriptions.return_value = sample_subscriptions
        mock_visor.bot.get_channel.return_value = mock_messageable_channel

        mock_details = {
            "name": "Test Game",
            "short_description": "A test game",
            "image": "https://example.com/image.jpg",
        }
        mock_visor.bot.itad_manager.find_game.return_value = None

        with (
            patch("bounty_discord.cogs.visor.resolve_game_details", return_value=mock_details),
            patch("bounty_discord.cogs.visor.create_game_embed") as mock_create_embed,
            patch("bounty_discord.cogs.visor._retry_send_message") as mock_send,
            patch("bounty_discord.cogs.visor.logger") as mock_logger,
        ):
            mock_embed = MagicMock()
            mock_create_embed.return_value = mock_embed

            mock_send.side_effect = Exception("Send failed")

            await mock_visor._announce_new(sample_items)

            # All 4 sends were attempted despite each one failing
            assert mock_send.call_count == 4

            # Exceptions were logged
            assert mock_logger.exception.call_count == 4

            # Posts still marked seen after all channels attempted
            assert mock_visor.bot.store.mark_post_seen.call_count == 2
