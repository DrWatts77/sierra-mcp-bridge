import json
import pytest
from sierra_mcp_bridge.setup import inspect_setup, validate_public_base


def test_preflight_readable_snapshot_and_pending_auth(setup_bridge):
    config, _, _ = setup_bridge
    result = inspect_setup(config, public_base='https://example.ngrok.app/', client='chatgpt', auth_provider='auth0',
                           find_executable=lambda _: 'ngrok.exe', port_available=lambda _: True)
    assert result.proposed_public_endpoint == 'https://example.ngrok.app/mcp'
    assert result.ready_for_public_exposure is False
    assert next(c for c in result.checks if c.stage == 'authentication').status == 'pending'
    assert 'snapshot_path' not in json.dumps(result.model_dump())
    assert config.charts[0].snapshot_path not in json.dumps(result.model_dump())


def test_preflight_missing_file_and_port_conflict(setup_bridge):
    config, path, _ = setup_bridge
    path.unlink()
    result = inspect_setup(config, find_executable=lambda _: None, port_available=lambda _: False)
    assert result.checks[0].status == 'blocked'
    assert next(c for c in result.checks if c.stage == 'local_port').status == 'attention'
    assert next(c for c in result.checks if c.stage == 'ngrok').status == 'blocked'


def test_entra_preflight_reports_implemented_but_unverified(setup_bridge):
    config, *_ = setup_bridge
    result = inspect_setup(config, auth_provider='entra', find_executable=lambda _: None,
                           port_available=lambda _: True)
    auth = next(c for c in result.checks if c.stage == 'authentication')
    assert 'adapter is implemented' in auth.message
    assert auth.status == 'pending'
    assert result.ready_for_public_exposure is False


@pytest.mark.parametrize('url', ['http://example.com', 'https://user:secret@example.com',
                                'https://example.com/mcp', 'https://example.com?token=secret',
                                'https://example.com/#fragment', 'https://bad host'])
def test_public_origin_rejects_unsafe_or_ambiguous_values(url):
    with pytest.raises(ValueError):
        validate_public_base(url)
