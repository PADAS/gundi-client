import pytest
from gundi_client_v2.client import GundiClient


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
