class GundiClientError(Exception):
    """Base exception for the Gundi client."""


class AuthenticationError(GundiClientError):
    """Raised when OAuth token retrieval or authentication fails."""


class GundiAPIError(GundiClientError):
    """Raised when the Gundi API returns a non-2xx response."""

    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}" if detail else f"HTTP {status_code}")
