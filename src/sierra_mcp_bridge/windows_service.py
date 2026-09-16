"""Optional NSSM service installation. Preview by default; no passwords on argv."""
import argparse
import csv
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

NAMES = ('SierraMCPBridge', 'SierraMCPTunnel')


def service_plan(root, nssm, ngrok, ngrok_config, owner_sid, owner_name, local_data):
    root = Path(root).resolve()
    profile = json.loads((root / 'connection.local.json').read_text(encoding='utf-8-sig'))
    if profile.get('auth') not in ('entra', 'none'):
        raise ValueError('Choose explicit entra or none authentication')
    from urllib.parse import urlsplit
    url = urlsplit(profile['public_url'])
    if url.scheme != 'https' or not url.hostname or url.path not in ('', '/') or url.query or url.fragment or url.username or url.password:
        raise ValueError('Invalid public HTTPS origin')
    port = profile['port']
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid port')
    if profile['auth'] == 'entra':
        from uuid import UUID
        UUID(profile['client_id']); UUID(profile['tenant_id'])
        callback = urlsplit(profile['client_redirect'])
        if callback.scheme != 'https' or not callback.hostname or callback.fragment or '*' in profile['client_redirect']:
            raise ValueError('Invalid exact client callback')
    settings = dict(profile, owner_sid=owner_sid, owner_name=owner_name,
        root=str(root), python=str(root / '.venv/Scripts/python.exe'),
        config=str(root / 'config.local.json'), ngrok=str(Path(ngrok).resolve()),
        ngrok_config=str(Path(ngrok_config).resolve()),
        secret=str(Path(local_data) / 'SierraMCPBridge/secrets/entra-client-secret.xml'),
        oauth_home=str(Path(local_data) / 'fastmcp'))
    settings_path = root / 'service.local.json'
    shell = str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
    commands = []
    entries = []
    for name, role in zip(NAMES, ('bridge', 'tunnel')):
        args = subprocess.list2cmdline(['-NoProfile', '-File', str(root / 'scripts/Run-SierraMCPService.ps1'),
                                       '-SettingsPath', str(settings_path), '-Role', role])
        entries.append(dict(name=name, application=shell, parameters=args))
        commands += [[str(nssm), 'install', name, shell],
                     [str(nssm), 'set', name, 'Start', 'SERVICE_DISABLED'],
                     [str(nssm), 'set', name, 'ObjectName', 'NT AUTHORITY\\LocalService']]
        for key, value in [('AppDirectory', str(root)), ('AppParameters', args),
                           ('AppExit', 'Default'), ('AppRestartDelay', '10000'),
                           ('AppThrottle', '10000'),
                           ('AppStdout', 'NUL'), ('AppStderr', 'NUL')]:
            command = [str(nssm), 'set', name, key, value]
            if key == 'AppExit': command.append('Restart')
            commands.append(command)
    commands.append([str(nssm), 'set', NAMES[1], 'DependOnService', NAMES[0]])
    return dict(settings=settings, settings_path=str(settings_path), entries=entries, commands=commands)


def decode_output(value):
    # NSSM 2.24 writes UTF-16LE to redirected handles; whoami uses the console codepage.
    if value.startswith(b'\xff\xfe') or b'\x00' in value:
        return value.decode('utf-16', errors='replace') if value.startswith(b'\xff\xfe') else value.decode('utf-16-le', errors='replace')
    return value.decode('mbcs' if os.name == 'nt' else 'utf-8', errors='replace')


def run(args):
    result = subprocess.run(args, capture_output=True, creationflags=0x08000000)
    if result.returncode:
        # Only surface operation/service/setting names, never raw environment or output.
        label = ' '.join(args[1:4]) if len(args) > 1 and args[1] == 'set' else ' '.join(args[1:3])
        raise RuntimeError('Service operation failed: ' + label + ' (exit ' + str(result.returncode) + ')')
    return decode_output(result.stdout).strip()


def exists(name):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SYSTEM\\CurrentControlSet\\Services\\' + name):
            return True
    except FileNotFoundError:
        return False


def current_identity():
    row = next(csv.reader([run(['whoami.exe', '/user', '/fo', 'csv', '/nh'])]))
    return row[0], row[1]


def service_parameter(name, key):
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SYSTEM\\CurrentControlSet\\Services\\' + name + '\\Parameters') as registry:
        return winreg.QueryValueEx(registry, key)[0]


def owned(record):
    for entry in record['entries']:
        if not exists(entry['name']):
            continue
        for key, expected in [('Application', entry['application']), ('AppParameters', entry['parameters'])]:
            actual = service_parameter(entry['name'], key)
            if actual != expected:
                raise RuntimeError('Service identity changed; refusing to manage ' + entry['name'])


def install_commands(plan, existing):
    for command in plan['commands']:
        if command[2] in existing and (command[1] == 'install' or command[3:4] == ['ObjectName']):
            continue
        yield command


def account_sid(account):
    # SCM accepts .\user, but NTAccount.Translate needs the computer name.
    if account.startswith('.\\'):
        account = os.environ['COMPUTERNAME'] + account[1:]
    script = "([Security.Principal.NTAccount]::new($env:SIERRA_SERVICE_ACCOUNT)).Translate([Security.Principal.SecurityIdentifier]).Value"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', script],
        env={**os.environ, 'SIERRA_SERVICE_ACCOUNT': account}, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Could not resolve the configured service Log On account')
    return result.stdout.strip()


def start_service(nssm, name, timeout=30):
    """NSSM can report failure while its throttled child is still starting."""
    start_error = None
    try:
        run([nssm, 'start', name])
    except RuntimeError as exc:
        start_error = exc
    deadline = time.monotonic() + timeout
    while True:
        state = run([nssm, 'status', name])
        if state == 'SERVICE_RUNNING':
            return
        if state not in ('SERVICE_START_PENDING', 'SERVICE_PAUSED', 'SERVICE_STOPPED'):
            raise RuntimeError('Service start did not complete: ' + name + ' (' + state + ')')
        if time.monotonic() >= deadline:
            detail = '; start command also reported failure' if start_error else ''
            raise RuntimeError('Service start timed out: ' + name + ' (' + state + ')' + detail)
        time.sleep(0.5)


def enable_services(record, port):
    nssm = record['nssm']
    states = {name: run([nssm, 'status', name]) for name in NAMES}
    if any(state not in ('SERVICE_RUNNING', 'SERVICE_STOPPED') for state in states.values()):
        raise RuntimeError('A service is transitioning or paused; check status before enabling')
    if states[NAMES[0]] == 'SERVICE_STOPPED':
        import socket
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(('127.0.0.1', port))
    for name in NAMES:
        run([nssm, 'set', name, 'Start', 'SERVICE_DELAYED_AUTO_START'])
        if states[name] == 'SERVICE_STOPPED':
            start_service(nssm, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'install', 'status', 'enable', 'restart', 'stop', 'uninstall'])
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--nssm', type=Path)
    parser.add_argument('--ngrok', type=Path)
    parser.add_argument('--ngrok-config', type=Path)
    args = parser.parse_args()
    if os.name != 'nt': parser.error('Windows service support requires Windows')
    root = args.root.resolve()
    record_path = root / 'service-install.local.json'
    try:
        if args.action not in ('plan', 'status') and not ctypes.windll.shell32.IsUserAnAdmin():
            raise RuntimeError('Run this command in an administrator PowerShell window')
        if args.action in ('plan', 'install'):
            if not all((args.nssm, args.ngrok, args.ngrok_config)):
                raise ValueError('Supply --nssm, --ngrok and --ngrok-config explicitly')
            owner_name, owner_sid = current_identity()
            plan = service_plan(root, args.nssm.resolve(), args.ngrok, args.ngrok_config,
                                owner_sid, owner_name, os.environ['LOCALAPPDATA'])
            if args.action == 'plan':
                print(json.dumps(dict(services=list(NAMES), owner=owner_name,
                    startup='Disabled until service logon is configured, then delayed automatic',
                    settings_path=plan['settings_path'], commands=plan['commands']), indent=2))
                return
            existing = {n for n in NAMES if exists(n)}
            if existing and not record_path.exists():
                raise RuntimeError('Services exist without our ownership record; refusing to overwrite them')
            if record_path.exists():
                old_record = json.loads(record_path.read_text())
                if (old_record['entries'] != plan['entries'] or old_record['owner_sid'] != owner_sid
                        or old_record['nssm'] != str(args.nssm.resolve())):
                    raise RuntimeError('Existing installation does not match this plan; refusing to overwrite it')
                owned(old_record)
                for name in existing:
                    if run([old_record['nssm'], 'status', name]) != 'SERVICE_STOPPED':
                        raise RuntimeError('Stop the existing services before repairing installation')
            required = [args.nssm, args.ngrok, args.ngrok_config, Path(plan['settings']['python']),
                        root/'config.local.json', root/'scripts/Run-SierraMCPService.ps1']
            if plan['settings']['auth'] == 'entra': required.append(Path(plan['settings']['secret']))
            if not all(p.is_file() for p in required):
                raise ValueError('A required executable, config, runner or encrypted secret is missing')
            # Installation does not stop manual listeners or start the new services.
            Path(plan['settings_path']).write_text(json.dumps(plan['settings'], indent=2))
            record = dict(nssm=str(args.nssm.resolve()), entries=plan['entries'], owner_sid=owner_sid,
                          owner_name=owner_name)
            record_path.write_text(json.dumps(record, indent=2))
            try:
                for command in install_commands(plan, existing): run(command)
            except RuntimeError as exc:
                # Keep ownership record so an incomplete installation is reviewable/removable.
                raise RuntimeError('Installation incomplete. ' + str(exc) + '. Services were not started; retry install after correcting the reported setting') from None
            print('Installed disabled. In services.msc, set BOTH service Log On accounts to ' + owner_name +
                  ' and enter the Windows password there. Then run enable. No password belongs in chat.')
            return
        record = json.loads(record_path.read_text())
        owned(record)
        if args.action == 'status':
            for name in NAMES:
                print(name + ': ' + (run([record['nssm'], 'status', name]) if exists(name) else 'not installed'))
            print('Running is process status, not proof of fresh Sierra data or a successful MCP call.')
            return
        if args.action in ('enable', 'restart'):
            # Compare account SIDs, including aliases used for the same Windows account.
            for name in NAMES:
                account = run([record['nssm'], 'get', name, 'ObjectName'])
                if account_sid(account) != record['owner_sid']:
                    raise RuntimeError('Configure both services to use the recorded Windows account before enabling')
            if args.action == 'restart':
                for name in reversed(NAMES):
                    if run([record['nssm'], 'status', name]) != 'SERVICE_STOPPED': run([record['nssm'], 'stop', name])
            settings = json.loads((root/'service.local.json').read_text())
            enable_services(record, settings['port'])
            print('Services enabled with delayed automatic startup; already-running services preserved. Verify an authenticated MCP read.')
        else:
            for name in reversed(NAMES):
                if exists(name):
                    if run([record['nssm'], 'status', name]) != 'SERVICE_STOPPED': run([record['nssm'], 'stop', name])
                    if args.action == 'uninstall': run([record['nssm'], 'remove', name, 'confirm'])
            if args.action == 'uninstall': record_path.unlink()
            print('Services ' + ('removed; configuration and secrets preserved.' if args.action == 'uninstall' else 'stopped.'))
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        # Do not print settings contents, subprocess output or credential values.
        parser.exit(1, 'Service setup did not complete. ' + (str(exc) if isinstance(exc, RuntimeError) else 'Check profile and required paths.') + '\n')


if __name__ == '__main__': main()
