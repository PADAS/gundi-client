import httpx


class GundiClientError(Exception):
    """Base exception for the Gundi client."""


class AuthenticationError(GundiClientError):
    """Raised when OAuth token retrieval or authentication fails."""


class GundiAPIError(GundiClientError):
    """Raised when the Gundi API returns a 4xx or 5xx HTTP response.

    Attributes:
        status_code: The HTTP status code from the response.
        detail: The response body text (often the API's error description),
            or an empty string when the response carried no body.
    """

    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}" if detail else f"HTTP {status_code}")


def raise_for_status(response):
    """Raise GundiAPIError for a 4xx/5xx httpx response, preserving the original error.

    Mirrors httpx.Response.raise_for_status(), which raises only for client/server
    error statuses (3xx redirects do not raise).
    """
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise GundiAPIError(
            status_code=e.response.status_code,
            detail=e.response.text,
        ) from e
