class BountyException(Exception):
    """Base exception for all BountyHunter core errors."""


class NetworkError(BountyException):
    """Raised when a low-level network error occurs (DNS, Connection Refused)."""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error


class GameNotFound(BountyException):
    """Raised when a game cannot be found in the store/API (404 or empty search)."""

    def __init__(self, identifier: str, store: str):
        super().__init__(f"Game '{identifier}' not found on {store}.")
        self.identifier = identifier
        self.store = store


class AccessDenied(BountyException):
    """
    Raised when the server refuses the request (403 Forbidden / 401 Unauthorized).
    This usually indicates a WAF block (Cloudflare) or bad API credentials.
    """

    def __init__(self, store: str, status_code: int):
        super().__init__(f"Access denied for {store} (Status: {status_code}). Check credentials or WAF.")
        self.store = store
        self.status_code = status_code


class RateLimitExceeded(BountyException):
    """Raised when an API rate limit is hit (429)."""

    def __init__(self, store: str, retry_after: float | None = None):
        msg = f"Rate limit exceeded for {store}."
        if retry_after:
            msg += f" Retry after {retry_after}s."
        super().__init__(msg)
        self.store = store
        self.retry_after = retry_after


class ScrapingError(BountyException):
    """Raised when the HTML structure is unexpected or parsing fails."""

    def __init__(self, store: str, item: str, details: str):
        super().__init__(f"Failed to scrape {store} for '{item}': {details}")
        self.store = store
        self.item = item


class APIError(BountyException):
    """Raised when an API returns an unexpected error (5xx, etc)."""

    def __init__(self, store: str, status_code: int | None = None, message: str = "Unknown error"):
        msg = f"{store} API Error"
        if status_code:
            msg += f" ({status_code})"
        msg += f": {message}"
        super().__init__(msg)
        self.store = store
        self.status_code = status_code
