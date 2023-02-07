import pytest
from aioresponses import aioresponses
from gundi_client.client import PortalApi


@pytest.fixture
def mock_aioresponse():
    with aioresponses() as m:
        yield m


@pytest.fixture
def gundi_client():
    return PortalApi()


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
def inbound_integration_config():
    return {
        "state": {},
        "id": "11115b4f-88cd-49c4-a723-0ddff1f580c4",
        "type": "b069e5bd-a473-4c02-9227-27b6134615a4",
        "owner": "088a191a-bcf3-471b-9e7d-6ba8bc71be9e",
        "endpoint": "https://logins.testbidtrack.co.za/restintegration/",
        "login": "test",
        "password": "test",
        "token": "",
        "type_slug": "bidtrack",
        "provider": "bidtrack",
        "default_devicegroup": "1111cfdc-1aae-44b0-8e0a-22c72355ea85",
        "enabled": True,
        "name": "BidTrack - Manyoni",
    }


@pytest.fixture
def outbound_integration_config_list():
    return [
        {
            "id": "2222dc7e-73e2-4af3-93f5-a1cb322e5add",
            "type": "f61b0c60-c863-44d7-adc6-d9b49b389e69",
            "owner": "1111191a-bcf3-471b-9e7d-6ba8bc71be9e",
            "name": "[Internal] AI2 Test -  Bidtrack to  ER",
            "endpoint": "https://cdip-er.pamdas.org/api/v1.0",
            "state": {},
            "login": "",
            "password": "",
            "token": "1111d87681cd1d01ad07c2d0f57d15d6079ae7d7",
            "type_slug": "earth_ranger",
            "inbound_type_slug": "bidtrack",
            "additional": {},
        }
    ]


@pytest.fixture
def outbound_integration_config():
    return {
        "id": "2222dc7e-73e2-4af3-93f5-a1cb322e5add",
        "type": "f61b0c60-c863-44d7-adc6-d9b49b389e69",
        "owner": "1111191a-bcf3-471b-9e7d-6ba8bc71be9e",
        "name": "[Internal] AI2 Test -  Bidtrack to  ER",
        "endpoint": "https://cdip-er.pamdas.org/api/v1.0",
        "state": {},
        "login": "",
        "password": "",
        "token": "1111d87681cd1d01ad07c2d0f57d15d6079ae7d7",
        "type_slug": "earth_ranger",
        "inbound_type_slug": "bidtrack",
        "additional": {},
    }
