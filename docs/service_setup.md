# Windows service setup — development preview

Optional alpha feature. Installation, account/DPAPI access, enable recovery and authenticated remote reads have worked on one installation. Full restart/reboot/logoff and recovery checks remain open. NSSM is not bundled; verify manual startup first.

## Preparation and human steps

The manager automatically checks `bin/nssm.exe` before PATH. Supplying `-NssmPath` overrides discovery. NSSM is not bundled in the source repository; obtain and review it separately.

1. Obtain a reviewed Windows x64 NSSM executable from its official distribution, store it permanently, and supply its path. Do not move/delete it after service registration. An explicit executable path is supported.
2. Keep the current connection.local.json and config.local.json. Use the same Windows account that saved the DPAPI Entra secret; this initial service mode does not support migration to another service identity. The installer records explicit paths for the secret, OAuth data and ngrok configuration.
3. Preview (ordinary PowerShell): `powershell -NoProfile -File scripts/Manage-SierraMCPService.ps1 -Action plan -NssmPath '<absolute-nssm-path>'`. Optional `-NgrokConfig` selects the existing ngrok YAML without displaying its contents. Default is the current user's LocalAppData ngrok/ngrok.yml. Preview does not validate a supplied binary or install/start services.
4. Run the same command with `-Action install` in an **administrator PowerShell window under the same Windows account**. It registers SierraMCPBridge and SierraMCPTunnel as disabled, with persistent foreground runners. It does not change or stop existing manual processes.
5. Open `services.msc`. For BOTH services, Properties > Log On > This account: enter the owner account printed by installation and its Windows account password (not a PIN). Windows handles that credential; never put it in chat or command-line arguments. Services must have permission to log on as a service and read the selected files. Passwordless/user-policy restrictions require an alternative identity/secret design; do not switch to LocalSystem to work around them.
6. Stop the manual bridge/tunnel with Stop-SierraMCPExposure.ps1 (or close old manual consoles). Then run `Manage-SierraMCPService.ps1 -Action enable` as administrator. It checks the service-account SIDs, enables delayed automatic startup, and starts both. Port conflict rejects enable rather than killing other processes.
7. Run `-Action status`, then an actual MCP tool call. Status reports service state, local/public readiness and snapshot preflight; service Running does not mean Sierra exports are fresh.

## Operation

If installation fails partway, rerun `-Action install` after correcting the reported issue. It repairs only stopped services with matching recorded owner, executable and parameters; existing logon credentials are preserved. NSSM 2.24 does not accept AppKillProcessTree, so this installer uses default stop handling. Real child-process cleanup remains an acceptance test.

Use `-Action restart`, `-Action stop`, or `-Action uninstall` from an administrator shell. Uninstall preserves local configs, encrypted secret and OAuth state; it removes only matching recorded services. Names are fixed for the first service profile, so multiple simultaneous service installations are not yet supported.

NSSM owns the foreground process trees and restarts unexpected exits with a 10-second delay/throttle. Logs are discarded to avoid unbounded output and secrets in logs. Use foreground launchers for detailed diagnosis. Service enablement is persistent until disabled/uninstalled; stop alone stops the current run and does not disable next-boot auto-start.

Sierra remains an interactive desktop application. The bridge can start before Sierra, return unavailable/stale data and recover as exports resume. Service mode does not open chartbooks or automate trading. A service account or Windows password change may require reconfiguration. Profile changes require reinstall/review because service.local.json is a captured configuration. Do not run manual and service modes on the same port concurrently.

## Broader live validation

Administrator install, logon/DPAPI access, authenticated tool call, restart and refresh continuity, reboot/logoff, Sierra closed/reopened, ngrok outage/recovery, stop child cleanup, partial-install removal and uninstall. Unit tests of generated commands are not evidence of these outcomes. Test one local owner/Entra/ngrok installation before advertising general unattended support.

Account aliases such as `.\owner` are accepted when they resolve to the recorded owner SID. Running `enable` again preserves running services and applies delayed automatic startup; it starts only stopped services. Transitional/paused states require review with `status`.

Use dependency order: enable preserves running services and starts stopped services bridge then tunnel; restart stops tunnel then bridge and starts bridge then tunnel; stop stops tunnel then bridge. The tunnel depends on the bridge. Start waits up to 30 seconds for Running, including after a nonzero NSSM result; process state is not authenticated readiness.
