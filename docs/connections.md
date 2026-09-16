# Connections and authentication

Authentication and exposure are separate choices. An HTTPS tunnel does not replace application authorization. External clients choose the model; the bridge needs no LLM API key.

| Option | Implementation and evidence |
| --- | --- |
| Local stdio | Implemented; local client owns process access |
| Explicit anonymous HTTP (`--auth none`) | Implemented; local protocol/tool calls tested; public anonymous client validation pending |
| Loopback HTTP development bearer token | Implemented/tested; not a public deployment profile |
| Microsoft Entra + local bridge + ngrok + ChatGPT | Implemented; successful remote study/history response reported on one installation |
| Auth0 | FastMCP capability; bridge adapter and end-to-end tests pending |
| Other OIDC providers | Future configurable adapters; not currently supported by bridge CLI |
| Cloudflare Tunnel | Planned; no tested launcher/profile |
| Hosted service | Future; requires authenticated delivery of Windows chart data |

## Startup status

Optional automatic startup tooling is available as a development preview: see [Windows service setup](service_setup.md). It requires NSSM, administrator installation and service-account configuration. Service installation/enable and authenticated reads worked on one installation; full restart/reboot and recovery checks remain open.

`-NoProfile` skips PowerShell's personal startup customizations (aliases/functions/environment initialization), not `connection.local.json`. This keeps launcher behavior independent of an interactive shell profile.

Readiness failures report the stage and safe reason: HTTP status, network/TLS failure, non-JSON/browser-warning response or issuer mismatch. Probes request JSON and use ngrok's documented browser-warning bypass header; OAuth and TLS certificate validation stay enabled. A successful local check followed by public failure means the public route needs diagnosis, not automatically that Entra credentials are wrong. Failed startup stops newly recorded processes, so later requests can show the endpoint offline.

Use `Start-SierraMCPExposure.ps1` to start the Python bridge and ngrok together. Copy `connection.example.json` to `connection.local.json` and enter your auth mode, public URL, port and Entra identifiers. The Entra secret still uses the encrypted store described below. For anonymous mode set `auth` to `none`; Entra fields are unused.

```powershell
powershell -NoProfile -File .\scripts\Start-SierraMCPExposure.ps1
powershell -NoProfile -File .\scripts\Stop-SierraMCPExposure.ps1
```

Start validates local protocol/auth readiness before launching ngrok and checks public readiness before displaying the URL. Both processes run hidden. Stop checks recorded PID, start time and executable path, and targets only those processes. Existing listeners are rejected, not killed or adopted. Close old manual bridge/ngrok windows before switching to this launcher. Failed startup cleans up newly recorded processes. No persistent logs are collected; foreground commands below remain useful for diagnosis. State and locking live under ignored `runtime/`. Duplicate start is rejected; stop is repeatable. Mocked Windows PowerShell lifecycle checks pass; real combined Entra/ngrok restart acceptance remains pending.

`Start-EntraBridge.ps1` remains the standalone foreground Entra server launcher. The two-window procedure below is the manual alternative.

Anonymous HTTP is available only when explicitly selected with `--auth none`. The default still requires a development bearer token; Entra is selected with `--auth entra`. Choosing no authentication in an MCP client alone does not change server settings. Anyone who can reach an anonymous endpoint can read the configured charts, including through a public tunnel. This option applies to the current read-only toolset.

## Local clients over stdio

An MCP-capable local application can launch the server as a subprocess; no HTTP, tunnel or OAuth is required. The client supplies model access and MCP tool execution; a bare LLM inference endpoint is not itself an MCP client.

```powershell
uv run --locked sierra-mcp-bridge --config config.local.json --transport stdio --auth none
```

Configure the client with the absolute path to `.venv/Scripts/python.exe` as its command and arguments `-m sierra_mcp_bridge.server --config <absolute-config-path> --transport stdio --auth none`. Using absolute paths avoids dependence on the client's working directory. Stdout is reserved for protocol messages.

## Anonymous Streamable HTTP

```powershell
uv run --locked sierra-mcp-bridge --config config.local.json --transport http --auth none --port 8765
```

Connect a local HTTP client to `http://127.0.0.1:8765/mcp` with no authentication. If deliberately exposing it through ngrok, run the same ngrok command documented below and use its HTTPS `/mcp` endpoint with authentication=None. No Entra registration or secret is required for this profile. Stop any existing server on that port first; this command does not alter running processes. Anonymous HTTP does not use `Start-EntraBridge.ps1`, which always selects Entra.

## Entra registration and foreground startup

Register your own application, initially single-tenant. Set Application ID URI `api://<client-id>`, add enabled delegated scope `market.read`, and set `api.requestedAccessTokenVersion` to `2`. Choose consent policy appropriate to your installation; the first tested setup used admin consent. Microsoft Graph/OneDrive permissions are not required.

Choose a stable public HTTPS hostname. Register a **Web** redirect URI `https://<host>/auth/callback`. Leave implicit token issuance disabled. This callback belongs to the bridge; the MCP client's callback is a separate allowlist.

Create a client secret, then run:

```powershell
.\scripts\Set-EntraClientSecret.ps1
```

Paste the secret VALUE into the hidden prompt. Windows DPAPI protects the stored SecureString for the current user/computer at `%LOCALAPPDATA%\SierraMCPBridge\secrets\entra-client-secret.xml`. The running process necessarily holds credentials in memory; this does not protect against a compromised Windows account. Secret expiry/rotation requires operational management. Multiple instances currently share this secret-store location and need a future per-instance profile.

Start the bridge in one PowerShell window:

```powershell
.\scripts\Start-EntraBridge.ps1 -ClientId '<client-id>' -TenantId '<tenant-id>' -PublicUrl 'https://<host>'
```

It binds to `127.0.0.1:8765`. Its default exact client redirect is `https://chatgpt.com/connector_platform_oauth_redirect`; use `-ClientRedirect` for another verified client callback. Do not enter the Entra secret into the MCP client. FastMCP manages OAuth proxy state with encrypted local persistence. Existing tenant policy and admin consent determine who can sign in; this is a single-owner bridge, not per-user chart isolation.

After configuring ngrok locally with your own account, run in a second window:

```powershell
ngrok http 8765 --url=https://<host> --inspect=false
```

Use the assigned ngrok development domain or a domain configured for your account. Both processes must be running before the client can discover OAuth. Connect the client to `https://<host>/mcp` with OAuth, then complete consent/sign-in. For ChatGPT, enable the connection and ask it to call `get_startup_context`, discover charts/studies and retrieve their current values/history. Compare results to Sierra.

Ctrl+C stops each foreground process. Combined launch, owned-process shutdown, token refresh/expiry, independent restarts and reconnect remain validation work. An offline tunnel may appear as an OAuth discovery error; check reachability before changing the registration. Do not disable authentication to troubleshoot.

## References

- [FastMCP Entra](https://gofastmcp.com/integrations/azure)
- [FastMCP authentication](https://gofastmcp.com/servers/auth/authentication)
- [FastMCP multiple auth sources](https://gofastmcp.com/servers/auth/multi-auth)
- [ngrok domains](https://ngrok.com/docs/pricing-limits/free-plan-limits)

Multiple token verifiers are not an automatic multi-provider login screen. Future adapters must test discovery, issuer/audience/scope validation, denied access, refresh, revoke and reconnect separately.
