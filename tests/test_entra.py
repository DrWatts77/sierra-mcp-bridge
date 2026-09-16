import asyncio
import pytest
import httpx2 as httpx
from key_value.aio.stores.memory import MemoryStore
from fastmcp.server.auth.providers.azure import AzureProvider
from sierra_mcp_bridge import auth
from sierra_mcp_bridge.server import create_server


def environment():
    return {'SIERRA_ENTRA_CLIENT_ID': '11111111-1111-4111-8111-111111111111',
            'SIERRA_ENTRA_TENANT_ID': '22222222-2222-4222-8222-222222222222',
            'SIERRA_MCP_PUBLIC_URL': 'https://bridge.example.com',
            'SIERRA_ENTRA_CLIENT_SECRET': 'synthetic-test-secret-only-123456789',
            'SIERRA_MCP_CLIENT_REDIRECTS': '["https://chatgpt.com/connector_platform_oauth_redirect"]'}


@pytest.mark.parametrize('key,value', [
    ('SIERRA_MCP_PUBLIC_URL', 'http://bridge.example.com'),
    ('SIERRA_ENTRA_TENANT_ID', 'common'),
    ('SIERRA_ENTRA_CLIENT_SECRET', ''),
    ('SIERRA_MCP_CLIENT_REDIRECTS', '[]'),
    ('SIERRA_MCP_CLIENT_REDIRECTS', '["https://*.example.com/callback"]'),
])
def test_reject_invalid_profile(key, value):
    env = environment()
    env[key] = value
    with pytest.raises(ValueError):
        auth.entra_provider(env)


def test_discovery_and_denial(monkeypatch, setup_bridge):
    monkeypatch.setattr(auth, 'AzureProvider', lambda **kw: AzureProvider(**kw, client_storage=MemoryStore()))
    provider = auth.entra_provider(environment())
    config, _, _ = setup_bridge
    server = create_server(config, auth=provider)
    with pytest.raises(ValueError):
        create_server(config, token='x' * 40, auth=provider)

    async def check():
        app = server.http_app(path='/mcp')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://bridge.example.com') as client:
            metadata = await client.get('/.well-known/oauth-authorization-server')
            assert metadata.status_code == 200
            assert metadata.json()['issuer'] == 'https://bridge.example.com/' or metadata.json()['issuer'] == 'https://bridge.example.com'
            assert 'S256' in metadata.json()['code_challenge_methods_supported']
            denied = await client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
            assert denied.status_code == 401
            assert 'resource_metadata=' in denied.headers['www-authenticate']
            denied_token = await client.post('/mcp', headers={'Authorization': 'Bearer invalid'}, json={})
            assert denied_token.status_code == 401
    asyncio.run(check())
