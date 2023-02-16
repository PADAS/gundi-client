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
import aiohttp
from gundi_client import PortalApi

async with aiohttp.ClientSession() as session:
    try:
        response = await portal.get_outbound_integration_list(
            session=session, inbound_id=str(inbound_id), device_id=str(device_id)
        )
    except aiohttp.ServerTimeoutError as e:
        logger.error("Read Timeout")              
        ...
    except aiohttp.ClientResponseError as e:
        logger.exception("Failed to get outbound integrations for inbound_id")
        ..
    else:
        # response contains a list configs as dicts
        for integration in response:  
            .. 
```
