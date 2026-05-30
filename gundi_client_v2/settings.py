import os
from environs import Env

envfile = os.environ.get("GUNDI_CLIENT_ENVFILE", None)

env = Env()

if envfile:
    env.read_env(envfile)
else:
    # Default behavior
    env.read_env()

# OAuth settings — OAUTH_* preferred; KEYCLOAK_* accepted for backward compatibility.
# The token URL is either set directly via OAUTH_TOKEN_URL or discovered at runtime
# from OAUTH_ISSUER via the OIDC discovery document.
OAUTH_ISSUER = env.str("OAUTH_ISSUER", env.str("KEYCLOAK_ISSUER", None))
OAUTH_TOKEN_URL = env.str("OAUTH_TOKEN_URL", None)
OAUTH_CLIENT_ID = env.str("OAUTH_CLIENT_ID", env.str("KEYCLOAK_CLIENT_ID", None))
OAUTH_CLIENT_SECRET = env.str("OAUTH_CLIENT_SECRET", env.str("KEYCLOAK_CLIENT_SECRET", None))
OAUTH_AUDIENCE = env.str("OAUTH_AUDIENCE", env.str("KEYCLOAK_AUDIENCE", None))
OAUTH_SCOPE = env.str("OAUTH_SCOPE", "openid")

# Backward-compatible aliases for the pre-rename setting names. Code importing
# gundi_client_v2.settings.KEYCLOAK_* keeps working; these mirror the OAUTH_* values.
KEYCLOAK_ISSUER = OAUTH_ISSUER
KEYCLOAK_CLIENT_ID = OAUTH_CLIENT_ID
KEYCLOAK_CLIENT_SECRET = OAUTH_CLIENT_SECRET
KEYCLOAK_AUDIENCE = OAUTH_AUDIENCE

GUNDI_API_BASE_URL = env.str("GUNDI_API_BASE_URL", None)
GUNDI_API_SSL_VERIFY = env.bool("GUNDI_API_SSL_VERIFY", True)

SENSORS_API_BASE_URL = env.str("SENSORS_API_BASE_URL", None)
GUNDI_USERNAME = env.str("GUNDI_USERNAME", None)
GUNDI_PASSWORD = env.str("GUNDI_PASSWORD", None)

LOG_LEVEL = env.log_level("LOG_LEVEL", "INFO")
