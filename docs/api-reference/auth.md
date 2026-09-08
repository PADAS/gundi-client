# auth

Standalone OAuth2 helpers. You normally don't call these directly —
`GundiClient` orchestrates them — but they're available if you need
fine-grained control.

::: gundi_client_v2.auth
    options:
      members:
        - get_access_token_client_credentials
        - get_access_token_password_grant
        - refresh_access_token
        - discover_token_endpoint
        - clear_discovery_cache

## `gundi_client_v2.token_cache`

::: gundi_client_v2.token_cache
    options:
      members:
        - CachedToken
        - TokenCache
        - MemoryTokenCache
        - RedisTokenCache
        - FileTokenCache
        - TokenStore
        - token_cache_from_url
        - token_cache_key
        - clear_token_cache
