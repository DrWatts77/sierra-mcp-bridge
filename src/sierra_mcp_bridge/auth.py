"""Explicit authentication profiles; no automatic fallback between providers."""
import json
from uuid import UUID
from urllib.parse import urlsplit
from fastmcp.server.auth.providers.azure import AzureProvider


def entra_provider(env):
    client_id = str(UUID(env['SIERRA_ENTRA_CLIENT_ID']))
    tenant_id = str(UUID(env['SIERRA_ENTRA_TENANT_ID']))
    base = env['SIERRA_MCP_PUBLIC_URL'].rstrip('/')
    url = urlsplit(base)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
        raise ValueError('Public URL must be an HTTPS origin')
    secret = env['SIERRA_ENTRA_CLIENT_SECRET']
    if not secret.strip():
        raise ValueError('Missing Entra secret')
    redirects = json.loads(env['SIERRA_MCP_CLIENT_REDIRECTS'])
    if not isinstance(redirects, list) or not redirects:
        raise ValueError('Explicit client redirect allowlist required')
    for redirect in redirects:
        if not isinstance(redirect, str) or '*' in redirect:
            raise ValueError('Exact client redirects required')
        parsed = urlsplit(redirect)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError('Invalid client redirect')
    return AzureProvider(client_id=client_id, tenant_id=tenant_id,
                         client_secret=secret, base_url=base,
                         required_scopes=['market.read'],
                         allowed_client_redirect_uris=redirects,
                         require_authorization_consent=True)
