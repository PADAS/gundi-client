# Gundi Client
## Introduction
[Gundi](https://www.earthranger.com/), a.k.a "The Portal" is a platform to manage integrations.
The gundi-client is an async python client to interact with Gundi's REST API.

## Installation
```
pip install gundi-client
```

## Usage

```
from gundi_client import PortalApi
import httpx

# You can use it as an async context-managed client
async with PortalApi() as portal:
   try:
    response = await portal.get_outbound_integration_list(
        session=session, inbound_id=str(inbound_id), device_id=str(device_id)
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
        # response contains a list configs as dicts
        for integration in response:  
            ...
   ...

# Or create an instance and close the client explicitly later
portal = PortalApi()
try:
    response = await portal.get_outbound_integration_list(
        session=session, inbound_id=str(inbound_id), device_id=str(device_id)
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
        # response contains a list configs as dicts
        for integration in response:  
            ...
   ...
   await portal.close()  # Close the session used to send requests to ER API
```
