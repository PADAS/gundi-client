import httpx


class GundiClientError(Exception):
    """Base exception for the Gundi client."""


class AuthenticationError(GundiClientError):
    """Raised when OAuth token retrieval or authentication fails.

    Attributes:
        status_code: The token endpoint's HTTP status when the failure was a
            non-2xx response, else None (network failure, malformed body,
            missing configuration).
        error: The RFC 6749 §5.2 ``error`` code from the response body when
            present (``invalid_grant``, ``invalid_client``, ...), else None.
        refresh_token_rejected: True when a refresh grant preceded this failure
            and the IdP answered it with 400 ``invalid_grant`` (the refresh token
            itself is dead), so callers can stop retrying it. False for a 5xx,
            a rate limit, a network failure, or when no refresh was attempted.
    """

    def __init__(
        self,
        message: str = "",
        *,
        status_code=None,
        error=None,
        refresh_token_rejected: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.refresh_token_rejected = refresh_token_rejected


class TokenCacheConfigError(GundiClientError):
    """Raised at construction when the token-cache configuration is unusable:
    an unsupported GUNDI_TOKEN_CACHE_URL, or a redis:// URL without the
    ``redis`` package installed (``pip install gundi-client-v2[redis]``)."""


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
        super().__init__(
            f"HTTP {status_code}: {detail}" if detail else f"HTTP {status_code}"
        )


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
