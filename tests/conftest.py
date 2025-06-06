import pytest
from gundi_client_v2.client import GundiClient, GundiDataSenderClient


@pytest.fixture
def sender_settings():
    return {
        "sensors_api_base_url": "https://sensors.api.fakerealm.gundi.org",
        "integration_api_key": "fake-api-key"
    }


@pytest.fixture
def client_settings():
    return {
        "oauth_token_url": "https://fakeauth.com/auth/realms/dev/protocol/openid-connect/token",
        "keycloak_audience": "fake-admin-portal",
        "keycloak_client_id": "fake-integration",
        "keycloak_client_secret": "84c4f67e-286e-48fc-9a2a-075312e6aa01",
        "base_url": "https://api.fakeportal.com"
    }


@pytest.fixture
def gundi_data_sender_client_v2(sender_settings):
    # Set env vars and initialize the gundi client
    return GundiDataSenderClient(**sender_settings)


@pytest.fixture
def gundi_client_v2(client_settings):
    # Set env vars and initialize the gundi client
    return GundiClient(**client_settings)


@pytest.fixture
def auth_token_response():
    return {
        "upgraded": False,
        "access_token": "TestToKeNiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJaS3lWZkFNRVhOZUhWT0hQQ0M2MVV6NzI2bnVBeDE0Tll0Zk5Qc3dTd0prIn0.eyJleHAiOjE2NzU3ODM1MzIsImlhdCI6MTY3NTc4MTczMiwianRpIjoiMjI4NGI4MWItNmM1OC00YzY0LThiMjItN2Y2YWY1NmY4YzYxIiwiaXNzIjoiaHR0cHM6Ly9jZGlwLWF1dGgucGFtZGFzLm9yZy9hdXRoL3JlYWxtcy9jZGlwLWRldiIsImF1ZCI6WyJjZGlwLWFkbWluLXBvcnRhbCIsImNkaXAtcm91dGluZyIsImFjY291bnQiXSwic3ViIjoiNzhmZGFlZDEtYjE1MC00ZWVkLWFmYjAtMzQ4YjczZDE2ODFmIiwidHlwIjoiQmVhcmVyIiwiYXpwIjoiY2RpcC1yb3V0aW5nIiwic2Vzc2lvbl9zdGF0ZSI6ImUwZGMzZWFlLTgyZDAtNDVjOS1hZjdmLThhY2ZlZDk3MTBkZiIsImFjciI6IjEiLCJhbGxvd2VkLW9yaWdpbnMiOlsiaHR0cDovL2xvY2FsaG9zdDozMDAwLyoiLCIqIl0sInJlYWxtX2FjY2VzcyI6eyJyb2xlcyI6WyJvZmZsaW5lX2FjY2VzcyIsImludGVncmF0aW9uIiwidW1hX2F1dGhvcml6YXRpb24iXX0sInJlc291cmNlX2FjY2VzcyI6eyJjZGlwLXJvdXRpbmciOnsicm9sZXMiOlsidW1hX3Byb3RlY3Rpb24iXX0sImFjY291bnQiOnsicm9sZXMiOlsibWFuYWdlLWFjY291bnQiLCJtYW5hZ2UtYWNjb3VudC1saW5rcyIsInZpZXctcHJvZmlsZSJdfX0sImF1dGhvcml6YXRpb24iOnsicGVybWlzc2lvbnMiOlt7InJzaWQiOiI2NjYxZmQ5MS1mMDBkLTQyZGYtOTQyYi05N2U3MWNlNjIwMTUiLCJyc25hbWUiOiJEZWZhdWx0IFJlc291cmNlIn0seyJzY29wZXMiOlsicmVhZCJdLCJyc2lkIjoiYWIxNzg5M2YtZmVkNi00YTQ1LTk2MWQtNDc1ZmE5ZTNkN2VmIiwicnNuYW1lIjoib3JnYW5pemF0aW9ucyJ9LHsic2NvcGVzIjpbInBhdGNoIiwicmVhZCIsInVwZGF0ZSJdLCJyc2lkIjoiN2U4ZTRmY2ItZDY5Yy00MTg3LTk5MTgtYzk0OTgxN2E5MTBiIiwicnNuYW1lIjoiaW5ib3VuZGludGVncmF0aW9uY29uZmlndXJhdGlvbiJ9LHsic2NvcGVzIjpbInJlYWQiXSwicnNpZCI6IjE4NGI1YTA3LWIzODctNDg4Ny1hNjRmLTE5MjQ5OTc4YTJmNCIsInJzbmFtZSI6Im91dGJvdW5kaW50ZWdyYXRpb250eXBlIn0seyJzY29wZXMiOlsicmVhZCJdLCJyc2lkIjoiNjcyNGI1ODktM2YxMC00ODRhLWE3Y2MtNTIwNmRlODZmOTdiIiwicnNuYW1lIjoib3V0Ym91bmRpbnRlZ3JhdGlvbmNvbmZpZ3VyYXRpb24ifSx7InNjb3BlcyI6WyJyZWFkIl0sInJzaWQiOiI0YzQ0Y2Y4NC0wNzA2LTRiYjAtOTQzMC0zN2I4NTc4ZTlhYjIiLCJyc25hbWUiOiJpbmJvdW5kaW50ZWdyYXRpb250eXBlIn1dfSwic2NvcGUiOiJwcm9maWxlIG9wZW5pZCByZWFsbS1tYW5hZ2VtZW50IGdpdmVuX25hbWUgZW1haWwgZmFtaWx5X25hbWUiLCJjbGllbnRIb3N0IjoiNDUuMTc2Ljg5LjI2IiwiY2xpZW50SWQiOiJjZGlwLXJvdXRpbmciLCJlbWFpbF92ZXJpZmllZCI6ZmFsc2UsInByZWZlcnJlZF91c2VybmFtZSI6InNlcnZpY2UtYWNjb3VudC1jZGlwLXJvdXRpbmciLCJjbGllbnRBZGRyZXNzIjoiNDUuMTc2Ljg5LjI2In0.LiXCMFwIhOk3EMWciE1Md0GpLaub7BWblNEfV5uy_vXPy6A6YD3d3LThaG7suFbxAGwSzYT_KFpDP4t9zvqU2UQ_DMWKbrF74LyDS631Td1GElqaAE7WJaVnqyWFZCrj4xccLhb39i-wlVIkCuE2ND_52o63La2MqWiJC9SXTMNqsc-LkdGih9MZ8aAepXvXZ_vhR8KQr5Ej6P1rawkx3jM0PRxt3i1Jvo6D5av6fIZrSnlD3D49dQXZonow5TQGzv1F1-nZZZ_AePrYpMUS_0Eyk-i_Po8IWPVyN03JlgamV6D6mIl2wXGJVdBXy66Lw8JvwQerLCixxtPsLiQBGQ",
        "expires_in": 1800,
        "refresh_expires_in": 43200,
        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICI2NzM0ZDU0MS0wZGE5LTRlZDctOGYwZS0yNWVjM2VlZGY5OTUifQ.eyJleHAiOjE2NzU4MjQ5MzIsImlhdCI6MTY3NTc4MTczMiwianRpIjoiYmRkZjU1NmMtZjhjOC00MjcxLTkwYzItOGU1MGIyZjM3YjM1IiwiaXNzIjoiaHR0cHM6Ly9jZGlwLWF1dGgucGFtZGFzLm9yZy9hdXRoL3JlYWxtcy9jZGlwLWRldiIsImF1ZCI6Imh0dHBzOi8vY2RpcC1hdXRoLnBhbWRhcy5vcmcvYXV0aC9yZWFsbXMvY2RpcC1kZXYiLCJzdWIiOiI3OGZkYWVkMS1iMTUwLTRlZWQtYWZiMC0zNDhiNzNkMTY4MWYiLCJ0eXAiOiJSZWZyZXNoIiwiYXpwIjoiY2RpcC1yb3V0aW5nIiwic2Vzc2lvbl9zdGF0ZSI6ImUwZGMzZWFlLTgyZDAtNDVjOS1hZjdmLThhY2ZlZDk3MTBkZiIsImF1dGhvcml6YXRpb24iOnsicGVybWlzc2lvbnMiOlt7InJzaWQiOiI2NjYxZmQ5MS1mMDBkLTQyZGYtOTQyYi05N2U3MWNlNjIwMTUiLCJyc25hbWUiOiJEZWZhdWx0IFJlc291cmNlIn0seyJzY29wZXMiOlsicmVhZCJdLCJyc2lkIjoiYWIxNzg5M2YtZmVkNi00YTQ1LTk2MWQtNDc1ZmE5ZTNkN2VmIiwicnNuYW1lIjoib3JnYW5pemF0aW9ucyJ9LHsic2NvcGVzIjpbInBhdGNoIiwicmVhZCIsInVwZGF0ZSJdLCJyc2lkIjoiN2U4ZTRmY2ItZDY5Yy00MTg3LTk5MTgtYzk0OTgxN2E5MTBiIiwicnNuYW1lIjoiaW5ib3VuZGludGVncmF0aW9uY29uZmlndXJhdGlvbiJ9LHsic2NvcGVzIjpbInJlYWQiXSwicnNpZCI6IjE4NGI1YTA3LWIzODctNDg4Ny1hNjRmLTE5MjQ5OTc4YTJmNCIsInJzbmFtZSI6Im91dGJvdW5kaW50ZWdyYXRpb250eXBlIn0seyJzY29wZXMiOlsicmVhZCJdLCJyc2lkIjoiNjcyNGI1ODktM2YxMC00ODRhLWE3Y2MtNTIwNmRlODZmOTdiIiwicnNuYW1lIjoib3V0Ym91bmRpbnRlZ3JhdGlvbmNvbmZpZ3VyYXRpb24ifSx7InNjb3BlcyI6WyJyZWFkIl0sInJzaWQiOiI0YzQ0Y2Y4NC0wNzA2LTRiYjAtOTQzMC0zN2I4NTc4ZTlhYjIiLCJyc25hbWUiOiJpbmJvdW5kaW50ZWdyYXRpb250eXBlIn1dfSwic2NvcGUiOiJwcm9maWxlIG9wZW5pZCByZWFsbS1tYW5hZ2VtZW50IGdpdmVuX25hbWUgZW1haWwgZmFtaWx5X25hbWUifQ.6dVK_WIM9sJR7jPG5E3rwEtUySAxw_TYJKJfVJl-FOY",
        "token_type": "Bearer",
        "not-before-policy": 1602633099,
    }


@pytest.fixture
def destination_integration_details():
    return {'id': '338225f3-91f9-4fe1-b013-353a229ce504', 'name': 'ER Load Testing',
            'base_url': 'https://gundi-load-testing.pamdas.org', 'enabled': True,
            'type': {'id': '45c66a61-71e4-4664-a7f2-30d465f87aa6', 'name': 'EarthRanger', 'value': 'earth_ranger',
                     'description': 'Integration type for Earth Ranger Sites', 'actions': [
                    {'id': '43ec4163-2f40-43fc-af62-bca1db77c06b', 'type': 'auth', 'name': 'Authenticate',
                     'value': 'auth',
                     'description': 'Authenticate against Earth Ranger',
                     'schema': {'type': 'object', 'required': ['token'], 'properties': {'token': {'type': 'string'}}}},
                    {'id': '036c2098-f494-40ec-a595-710b314d5ea5', 'type': 'pull', 'name': 'Pull Positions',
                     'value': 'pull_positions', 'description': 'Pull position data from an Earth Ranger site',
                     'schema': {'type': 'object', 'required': ['endpoint'],
                                'properties': {'endpoint': {'type': 'string'}}}},
                    {'id': '9286bb71-9aca-425a-881f-7fe0b2dba4f4', 'type': 'push', 'name': 'Push Events',
                     'value': 'push_events', 'description': 'EarthRanger sites support sending Events (a.k.a Reports)',
                     'schema': {}},
                    {'id': 'aae0cf50-fbc7-4810-84fd-53fb75020a43', 'type': 'push', 'name': 'Push Positions',
                     'value': 'push_positions', 'description': 'Push position data to an Earth Ranger site',
                     'schema': {'type': 'object', 'required': ['endpoint'],
                                'properties': {'endpoint': {'type': 'string'}}}}]},
            'owner': {'id': 'e2d1b0fc-69fe-408b-afc5-7f54872730c0', 'name': 'Test Organization', 'description': ''},
            'configurations': [
                {'id': '013ea7ce-4944-4f7e-8a2f-e5338b3741ce', 'integration': '338225f3-91f9-4fe1-b013-353a229ce504',
                 'action': {'id': '43ec4163-2f40-43fc-af62-bca1db77c06b', 'type': 'auth', 'name': 'Authenticate',
                            'value': 'auth'}, 'data': {'token': '1190d87681cd1d01ad07c2d0f57d15d6079ae7ab'}},
                {'id': '5de91c7b-f28a-4ce7-8137-273ac10674d2', 'integration': '338225f3-91f9-4fe1-b013-353a229ce504',
                 'action': {'id': 'aae0cf50-fbc7-4810-84fd-53fb75020a43', 'type': 'push', 'name': 'Push Positions',
                            'value': 'push_positions'}, 'data': {'endpoint': 'api/v1/positions'}},
                {'id': '7947b19e-1d2d-4ca3-bd6c-74976ae1de68', 'integration': '338225f3-91f9-4fe1-b013-353a229ce504',
                 'action': {'id': '036c2098-f494-40ec-a595-710b314d5ea5', 'type': 'pull', 'name': 'Pull Positions',
                            'value': 'pull_positions'}, 'data': {'endpoint': 'api/v1/positions'}}],
            'additional': {'topic': 'destination-v2-338225f3-91f9-4fe1-b013-353a229ce504-dev', 'broker': 'gcp_pubsub'},
            'default_route': {'id': '38dd8ec2-b3ee-4c31-940e-b6cc9c1f4326', 'name': 'Mukutan - Load Testing'},
            'status': {'id': 'mockid-b16a-4dbd-ad32-197c58aeef59', 'is_healthy': True,
                       'details': 'Last observation has been delivered with success.',
                       'observation_delivered_24hrs': 50231,
                       'last_observation_delivered_at': '2023-03-31T11:20:00+0200'}
            }

@pytest.fixture
def webhook_integration_details():
    return {
        "id": "817d3d4e-5dba-4792-8a30-a87603c5d201",
        "name": "Webhook Integration Test",
        "base_url": "",
        "enabled": True,
        "type": {
            "id": "f578b04d-2977-4774-959d-5a914a1a0ca3",
            "name": "LiquidTech",
            "value": "liquidtech",
            "description": "Default type for Liquidtech integration",
            "actions": [],
            "webhook": {
                "id": "c4b524d9-f01e-430f-a6f6-5459d95b5394",
                "name": "Generic Webhooks",
                "value": "webhook",
                "description": "Generic Webhooks Integration with JSON Transformations and hex data",
                "schema": {
                    "type": "object",
                    "title": "Data Transformation",
                    "required": [
                        "json_schema",
                        "jq_filter",
                        "output_type",
                        "hex_format",
                        "hex_data_field"
                    ],
                    "properties": {
                        "jq_filter": {
                            "type": "string",
                            "title": "Jq Filter",
                            "default": ".",
                            "example": ".",
                            "description": "JQ filter to transform JSON data to Gundi schema."
                        },
                        "hex_format": {
                            "type": "object",
                            "title": "Hex Format"
                        },
                        "json_schema": {
                            "type": "object",
                            "title": "Json Schema"
                        },
                        "output_type": {
                            "type": "string",
                            "title": "Output Type",
                            "description": "Output type for the transformed data: 'obv' or 'ev'"
                        },
                        "hex_data_field": {
                            "type": "string",
                            "title": "Hex Data Field"
                        }
                    }
                }
            }
        },
        "owner": {
            "id": "a91b400b-482a-4546-8fcb-ee42b01deeb6",
            "name": "Test Org",
            "description": ""
        },
        "configurations": None,
        "webhook_configuration": {
            "id": "c9af3525-7a6f-4611-91e5-0ed19a6c4736",
            "integration": "817d3d4e-5dba-4792-8a30-a87603c5d201",
            "webhook": {
                "id": "c4b524d9-f01e-430f-a6f6-5459d95b5394",
                "name": "LiquidTech Webhook",
                "value": "webhook"
            },
            "data": {
                "jq_filter": "{source: .device, title: .device,event_type: \"water_meter_rep\",recorded_at: (.time | tonumber | todateiso8601), location: {lat: 0.0,lon: 0.0},event_details: {}}",
                "hex_format": {
                    "fields": [
                        {
                            "name": "start_bit",
                            "format": "B",
                            "output_type": "int"
                        },
                        {
                            "name": "v",
                            "format": "I"
                        },
                        {
                            "name": "interval",
                            "format": "H",
                            "output_type": "int"
                        },
                        {
                            "name": "meter_state_1",
                            "format": "B"
                        },
                        {
                            "name": "meter_state_2",
                            "format": "B",
                            "bit_fields": [
                                {
                                    "name": "meter_batter_alarm",
                                    "end_bit": 0,
                                    "start_bit": 0,
                                    "output_type": "bool"
                                },
                                {
                                    "name": "empty_pipe_alarm",
                                    "end_bit": 1,
                                    "start_bit": 1,
                                    "output_type": "bool"
                                },
                                {
                                    "name": "reverse_flow_alarm",
                                    "end_bit": 2,
                                    "start_bit": 2,
                                    "output_type": "bool"
                                },
                                {
                                    "name": "over_range_alarm",
                                    "end_bit": 3,
                                    "start_bit": 3,
                                    "output_type": "bool"
                                },
                                {
                                    "name": "temp_alarm",
                                    "end_bit": 4,
                                    "start_bit": 4,
                                    "output_type": "bool"
                                },
                                {
                                    "name": "ee_error",
                                    "end_bit": 5,
                                    "start_bit": 5,
                                    "output_type": "bool"
                                },
                                {
                                    "name": "transduce_in_error",
                                    "end_bit": 6,
                                    "start_bit": 6,
                                    "output_type": "bool"
                                },
                                {
                                    "name": "transduce_out_error",
                                    "end_bit": 7,
                                    "start_bit": 7,
                                    "output_type": "bool"
                                },
                                {
                                    "name": "transduce_out_error",
                                    "end_bit": 7,
                                    "start_bit": 7,
                                    "output_type": "bool"
                                }
                            ]
                        },
                        {
                            "name": "r1",
                            "format": "B",
                            "output_type": "int"
                        },
                        {
                            "name": "r2",
                            "format": "B",
                            "output_type": "int"
                        },
                        {
                            "name": "crc",
                            "format": "B"
                        }
                    ],
                    "byte_order": "<"
                },
                "json_schema": {
                    "type": "object",
                    "title": "LiquidTechPayload",
                    "required": [
                        "device",
                        "time",
                        "data"
                    ],
                    "properties": {
                        "data": {
                            "type": "hex_string",
                            "title": "Data",
                            "example": "123456789ABCDEF",
                            "description": "Hex string data"
                        },
                        "time": {
                            "type": "string",
                            "title": "Time"
                        },
                        "type": {
                            "type": "string",
                            "title": "Type"
                        },
                        "device": {
                            "type": "string",
                            "title": "Device"
                        },
                        "hex_format": {
                            "type": "object",
                            "title": "Hex Format"
                        },
                        "hex_data_field": {
                            "type": "string",
                            "title": "Hex Data Field"
                        }
                    }
                },
                "output_type": "ev",
                "hex_data_field": "data"
            }
        },
        "additional": {},
        "default_route": None,
        "status": {
            "id": "mockid-b16a-4dbd-ad32-197c58aeef59",
            "is_healthy": True,
            "details": "Last observation has been delivered with success.",
            "observation_delivered_24hrs": 50231,
            "last_observation_delivered_at": "2023-03-31T11:20:00+0200"
        }
    }


@pytest.fixture
def connection_details():
    return {
        'id': 'ddd0946d-15b0-4308-b93d-e0470b6d33b6',
        'provider': {'id': 'ddd0946d-15b0-4308-b93d-e0470b6d33b6', 'name': 'Trap Tagger',
                     'owner': {'id': 'e2d1b0fc-69fe-408b-afc5-7f54872730c0', 'name': 'Test Organization'},
                     'type': {'id': '190e3710-3a29-4710-b932-f951222209a7', 'name': 'TrapTagger',
                              'value': 'traptagger'}, 'base_url': 'https://test.traptagger.com',
                     'status': 'healthy'}, 'destinations': [
            {'id': '338225f3-91f9-4fe1-b013-353a229ce504', 'name': 'ER Load Testing',
             'owner': {'id': 'e2d1b0fc-69fe-408b-afc5-7f54872730c0', 'name': 'Test Organization'},
             'type': {'id': '45c66a61-71e4-4664-a7f2-30d465f87aa6', 'name': 'EarthRanger', 'value': 'earth_ranger'},
             'base_url': 'https://gundi-load-testing.pamdas.org', 'status': 'healthy'}],
        'routing_rules': [{'id': '835897f9-1ef2-4d99-9c6c-ea2663380c1f', 'name': 'TrapTagger Default Route'}],
        'default_route': {'id': '835897f9-1ef2-4d99-9c6c-ea2663380c1f', 'name': 'TrapTagger Default Route'},
        'owner': {'id': 'e2d1b0fc-69fe-408b-afc5-7f54872730c0', 'name': 'Test Organization', 'description': ''},
        'status': 'healthy'
    }


@pytest.fixture
def route_details():
    return {
        'id': '835897f9-1ef2-4d99-9c6c-ea2663380c1f', 'name': 'TrapTagger Default Route',
        'owner': 'e2d1b0fc-69fe-408b-afc5-7f54872730c0', 'data_providers': [
            {'id': 'ddd0946d-15b0-4308-b93d-e0470b6d33b6', 'name': 'Trap Tagger',
             'owner': {'id': 'e2d1b0fc-69fe-408b-afc5-7f54872730c0', 'name': 'Test Organization'},
             'type': {'id': '190e3710-3a29-4710-b932-f951222209a7', 'name': 'TrapTagger', 'value': 'traptagger'},
             'base_url': 'https://test.traptagger.com', 'status': 'healthy'}], 'destinations': [
            {'id': '338225f3-91f9-4fe1-b013-353a229ce504', 'name': 'ER Load Testing',
             'owner': {'id': 'e2d1b0fc-69fe-408b-afc5-7f54872730c0', 'name': 'Test Organization'},
             'type': {'id': '45c66a61-71e4-4664-a7f2-30d465f87aa6', 'name': 'EarthRanger', 'value': 'earth_ranger'},
             'base_url': 'https://gundi-load-testing.pamdas.org', 'status': 'healthy'}],
        'configuration': {'id': '1a3e3e73-94ad-42cb-a765-09a7193ae0b1',
                          'name': 'Trap Tagger to ER - Event Type Mapping', 'data': {'field_mappings': {
                'ddd0946d-15b0-4308-b93d-e0470b6d33b6': {'ev': {'558225f3-91f9-4fe1-b013-353a229ce503': {
                    'map': {'Leopard': 'leopard_sighting', 'Wilddog': 'wild_dog_sighting'},
                    'default': 'wildlife_sighting_rep', 'provider_field': 'event_details__species',
                    'destination_field': 'event_type'}}}}}}, 'additional': {}
    }


@pytest.fixture
def observation_payload():
    return {
        'source': 123,
        'source_name': 'TEST',
        'type': 'tracking-device',
        'recorded_at': '2023-10-02 11:04:49',
        'location': {
            'lat': -20.398828,
            'lon': 14.263916
        },
        'additional': {
            'vehicleId': 555,
            'speed': 55,
            'direction': 281
        }
    }


@pytest.fixture
def observations_created_response():
    return [
        {
            "object_id": "96422ba3-3ea9-4b0d-8950-850e218e1140",
            "created_at": "2023-11-16T20:02:08.539777Z"
        }
    ]


@pytest.fixture
def event_payload():
    return {
        "title": "Animal Detected",
        "event_type": "wildlife_sighting_rep",
        "recorded_at":"2023-11-10T13:35-03:00",
        "location":{
            "lat":-51.688651,
            "lon":-72.704446
        },
        "event_details":{
            "site_name":"Camera2M",
            "species":"lion",
            "tags":[
                "adult",
                "male"
            ],
            "animal_count":2
        }
    }


@pytest.fixture
def message_payload():
    return {
        "sender": "2075752244",
        "recipients": ["admin@sitex.pamdas.org"],
        "text": "Assistance needed at the site.",
        "recorded_at": "2025-06-06 09:50:10-0300",
        "location": {
            "latitude": -51.689,
            "longitude": -72.717
        },
        "additional": {
            "status": {
                "autonomous": 0,
                "lowBattery": 1,
                "intervalChange": 0,
                "resetDetected": 0
            }
        }
    }


@pytest.fixture
def event_attachment_payload():
    # Representation of an image in binary format
    return ("file1.png", b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00x\x00x\x00\x00\xff\xdb\x00C\x00\x02\x01\x01\x02')


@pytest.fixture
def another_event_attachment_payload():
    # Representation of an image in binary format
    return ("file2.png", b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x06\x01\x01\x00x\x00x\x01\x00\xff\xd5\x00C\x00\x98\x01\x01\x56')


@pytest.fixture
def events_created_response():
    return [
        {
            "object_id": "abebe106-3c50-446b-9c98-0b9b503fc900",
            "created_at": "2023-11-16T19:59:50.612864Z"
        }
    ]

@pytest.fixture
def messages_created_response():
    return {
        "object_id": "998ac464-07d1-45af-8c5a-701d5171cc99",
        "created_at": "2025-06-06T18:48:27.207038Z",
        "updated_at": None
    }

@pytest.fixture
def event_attachment_created_response():
    return [
        {
            "object_id": "af8e2946-bad6-4d02-8a26-99dde34bd9fa",
            "created_at": "2024-07-04T13:15:26.559894Z",
            "updated_at": None
        }
    ]


@pytest.fixture
def trace_object_id():
    return '92855c84-572b-42ae-8183-8deb33fdd476'


@pytest.fixture
def trace_destination_id():
    return '338225f3-91f9-4fe1-b013-353a229ce504'


@pytest.fixture
def traces_list_response(trace_object_id, trace_destination_id):
    return {
        'next': None,
        'previous': None,
        'results': [
            {
                'object_id': trace_object_id,
                'object_type': 'ev',
                'related_to': None,
                'data_provider': 'ddd0946d-15b0-4308-b93d-e0470b6d33b6',
                'destination': trace_destination_id,
                'delivered_at': '2023-07-10T19:35:34.425974Z',
                'external_id': 'dbfd2e2b-45ae-4961-86b7-cd056217a22f',
                'created_at': '2023-07-10T19:20:43.977431Z',
                'updated_at': '2023-07-10T19:36:10.788527Z'
            }
        ]
    }
