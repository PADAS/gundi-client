__version__ = "2.6.0"

from .client import GundiClient, GundiDataSenderClient
from .errors import GundiClientError, AuthenticationError, GundiAPIError
from . import errors
