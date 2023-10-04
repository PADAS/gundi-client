import os
from environs import Env

envfile = os.environ.get("GUNDI_CLIENT_ENVFILE", None)

env = Env()

if envfile:
    env.read_env(envfile)
else:
    # Default behavior
    env.read_env()

KEYCLOAK_ISSUER = env.str("KEYCLOAK_ISSUER", None)
OAUTH_TOKEN_URL = f"{KEYCLOAK_ISSUER}/protocol/openid-connect/token"
KEYCLOAK_CLIENT_ID = env.str("KEYCLOAK_CLIENT_ID", None)
KEYCLOAK_CLIENT_SECRET = env.str("KEYCLOAK_CLIENT_SECRET", None)
KEYCLOAK_AUDIENCE = env.str("KEYCLOAK_AUDIENCE", None)

GUNDI_API_BASE_URL = env.str("GUNDI_API_BASE_URL", None)
GUNDI_API_SSL_VERIFY = env.bool("GUNDI_API_SSL_VERIFY", True)

SENSORS_API_BASE_URL = env.str("SENSORS_API_BASE_URL", None)
# How many items should be posted to Sensors API in each request.
INTEGRATION_LOAD_BATCH_SIZE = env.int("INTEGRATION_LOAD_BATCH_SIZE", 100)

LOG_LEVEL = env.log_level("LOG_LEVEL", "INFO")
