__version__ = "3.6.2"

from .client import GundiClient, GundiDataSenderClient
from .errors import GundiClientError, AuthenticationError, GundiAPIError
from . import errors
