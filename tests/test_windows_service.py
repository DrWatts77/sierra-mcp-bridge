import json
from pathlib import Path
import pytest
from sierra_mcp_bridge import windows_service as ws


@pytest.fixture
def service_root(tmp_path):
    (tmp_path/'connection.local.json').write_text(json.dumps(dict(auth='entra',port=8765,
        public_url='https://bridge.example.com',client_id='11111111-1111-4111-8111-111111111111',
        tenant_id='22222222-2222-4222-8222-222222222222',client_redirect='https://client.example.com/callback')))
    return tmp_path


def plan(root):
    return ws.service_plan(root, root/'nssm.exe', root/'ngrok.exe', root/'ngrok.yml',
                           'S-1-5-21-123', 'EXAMPLE\\owner', root/'userdata')


def test_plan_persistent_services_and_no_credentials(service_root):
    result=plan(service_root)
    commands=result['commands']
    assert len(result['entries']) == 2
    assert all('Run-SierraMCPService.ps1' in e['parameters'] for e in result['entries'])
    assert all('Start-SierraMCPExposure' not in e['parameters'] for e in result['entries'])
    assert sum(c[3:] == ['Start','SERVICE_DISABLED'] for c in commands)==2
    assert sum(c[3:] == ['AppRestartDelay','10000'] for c in commands)==2
    assert not any(c[1]=='start' for c in commands)
    assert not any('CLIENT_SECRET=' in str(c) for c in commands)
    assert not (service_root/'service.local.json').exists()


@pytest.mark.parametrize('field,value', [('auth','development'),('port',0),('port',True),
    ('public_url','http://bridge.example.com'),('public_url','https://user:password@bridge.example.com'),
    ('tenant_id','common'),('client_redirect','https://*.example.com/callback')])
def test_bad_service_profile(service_root,field,value):
    file=service_root/'connection.local.json'; data=json.loads(file.read_text()); data[field]=value; file.write_text(json.dumps(data))
    with pytest.raises(ValueError): plan(service_root)


def test_anonymous_profile_does_not_require_entra_fields(service_root):
    (service_root/'connection.local.json').write_text('{"auth":"none","port":8765,"public_url":"https://bridge.example.com"}')
    assert plan(service_root)['settings']['auth']=='none'


def test_existing_service_identity_is_checked(monkeypatch):
    monkeypatch.setattr(ws,'exists',lambda name:True)
    monkeypatch.setattr(ws,'service_parameter',lambda name,key:'unrelated.exe')
    with pytest.raises(RuntimeError,match='identity changed'):
        ws.owned(dict(nssm='nssm',entries=[dict(name='SierraMCPBridge',application='ours.exe',parameters='ours')]))


def test_nssm_224_compatible_plan_and_resume(service_root):
    result=plan(service_root)
    assert not any('AppKillProcessTree' in c for c in result['commands'])
    commands=list(ws.install_commands(result, {'SierraMCPBridge'}))
    assert not any(c[1:3]==['install','SierraMCPBridge'] for c in commands)
    assert any(c[1:3]==['install','SierraMCPTunnel'] for c in commands)
    assert not any(c[2:4]==['SierraMCPBridge','ObjectName'] for c in commands)
    assert any(c[2:5]==['SierraMCPBridge','AppStdout','NUL'] for c in commands)


def test_nssm_redirected_output_decoding():
    assert ws.decode_output('SERVICE_STOPPED\r\n'.encode('utf-16-le')).strip()=='SERVICE_STOPPED'
    assert ws.decode_output(b'SERVICE_STOPPED\r\n').strip()=='SERVICE_STOPPED'


@pytest.mark.parametrize('account,expected', [(r'.\owner', r'HOST\owner'),
    (r'DOMAIN\owner', r'DOMAIN\owner')])
def test_account_alias_resolution(monkeypatch, account, expected):
    from types import SimpleNamespace
    monkeypatch.setenv('COMPUTERNAME', 'HOST')
    def fake_run(args, **kwargs):
        assert kwargs['env']['SIERRA_SERVICE_ACCOUNT'] == expected
        assert account not in args
        return SimpleNamespace(returncode=0, stdout='S-1-5-21-123\r\n')
    monkeypatch.setattr(ws.subprocess, 'run', fake_run)
    assert ws.account_sid(account) == 'S-1-5-21-123'


def test_enable_preserves_running_services(monkeypatch):
    import socket
    commands = []
    def fake_run(args):
        commands.append(args)
        return 'SERVICE_RUNNING' if args[1] == 'status' else ''
    monkeypatch.setattr(ws, 'run', fake_run)
    monkeypatch.setattr(socket, 'socket', lambda: pytest.fail('Must not probe occupied port of running bridge'))
    ws.enable_services({'nssm': 'nssm'}, 8765)
    assert not any(c[1] in ('start', 'stop') for c in commands)
    assert sum(c[1] == 'set' for c in commands) == 2


def test_enable_starts_only_stopped_tunnel(monkeypatch):
    commands = []
    def fake_run(args):
        commands.append(args)
        if args[1] == 'status':
            started = any(c[1:3] == ['start', ws.NAMES[1]] for c in commands)
            return 'SERVICE_RUNNING' if args[2] == ws.NAMES[0] or started else 'SERVICE_STOPPED'
        return ''
    monkeypatch.setattr(ws, 'run', fake_run)
    ws.enable_services({'nssm': 'nssm'}, 8765)
    assert [c for c in commands if c[1] == 'start'] == [['nssm', 'start', ws.NAMES[1]]]


def test_enable_rejects_transition_without_changes(monkeypatch):
    commands = []
    def fake_run(args):
        commands.append(args)
        return 'SERVICE_START_PENDING'
    monkeypatch.setattr(ws, 'run', fake_run)
    with pytest.raises(RuntimeError, match='transitioning'):
        ws.enable_services({'nssm': 'nssm'}, 8765)
    assert all(c[1] == 'status' for c in commands)


@pytest.mark.parametrize('command_failed', [False, True])
def test_start_waits_for_nssm_transition(monkeypatch, command_failed):
    states = iter(['SERVICE_PAUSED', 'SERVICE_START_PENDING', 'SERVICE_RUNNING'])
    commands = []
    def fake_run(args):
        commands.append(args)
        if args[1] == 'start' and command_failed:
            raise RuntimeError('Service operation failed: start bridge (exit 1)')
        return next(states) if args[1] == 'status' else ''
    monkeypatch.setattr(ws, 'run', fake_run)
    monkeypatch.setattr(ws.time, 'sleep', lambda _: None)
    ws.start_service('nssm', ws.NAMES[0])
    assert sum(c[1] == 'start' for c in commands) == 1
    assert sum(c[1] == 'status' for c in commands) == 3


def test_start_timeout_does_not_silently_succeed(monkeypatch):
    def fake_run(args):
        if args[1] == 'start':
            raise RuntimeError('start failed')
        return 'SERVICE_STOPPED'
    monkeypatch.setattr(ws, 'run', fake_run)
    with pytest.raises(RuntimeError, match='timed out.*SERVICE_STOPPED'):
        ws.start_service('nssm', ws.NAMES[0], timeout=0)
