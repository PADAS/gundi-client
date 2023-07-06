# Gundi Client
## Introduction
[Gundi](https://www.earthranger.com/), a.k.a "The Portal" is a platform to manage integrations.
The gundi-client is an async python client to interact with Gundi's REST API.

## Installation
```
pip install gundi-client-v2
```

## Usage

```
from gundi_client_v2 import GundiClient
import httpx

# You can use it as an async context-managed client
async with GundiClient() as client:
   try:
    connection = await client.get_connection_details(
        integration_id="some-integration-uuid"
    )
    except httpx.RequestError as e:
        logger.exception("Request Error")   
        ...
    except httpx.TimeoutException as e:
        logger.exception("Request timed out")
        ...
    except httpx.HTTPStatusError as e:
        logger.exception("Response returned error")
    else:
        for integration in connection.destinations:  
            ...
   ...

# Or create an instance and close the client explicitly later
client = GundiClient()
try:
    response = await client.get_connection_details(
        integration_id="some-integration-uuid"
    )
    except httpx.RequestError as e:
        logger.exception("Request Error")   
        ...
    except httpx.TimeoutException as e:
        logger.exception("Request timed out")
        ...
    except httpx.HTTPStatusError as e:
        logger.exception("Response returned error")
    else:
        for integration in connection.destinations:
            ...
   ...
   await client.close()  # Close the session used to send requests to Gundi
```
