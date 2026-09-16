# Installation

## Requirements

Windows, Sierra Chart with ACSIL build support, an x64 compiler supported by your
Sierra installation, Python 3.12–3.14 and uv. Validation used Sierra v2949,
Python 3.12 and Visual Studio 2026 Build Tools. Other combinations need testing.
Obtain Sierra, its headers and compiler separately; only our source is included.

Clone/download into a separate project folder. Do not initialize Git in Sierra's
Data folder or copy the Sierra installation into this repository.

## Build and attach the exporter

1. Copy `acsil/sierra_mcp_bridge.cpp` into Sierra's `ACS_Source`. Preserve prior
   source if needed for rollback.
2. Build through Sierra's custom-study workflow using installed headers.
3. Add **Sierra MCP Bridge** once to each desired chart.
4. Select study IDs/subgraphs in the eight export slots. Study ID 0 disables a slot.
   Merely adding a study to a chart does not select it for export.
5. Leave **Snapshot output path** blank. The file is
   `<Sierra Data>/SierraMCPBridge/mcp_<export_id>.json`. Save the chartbook after
   first export. Check Sierra's Message Log for errors.

Rebuild/reload updates existing instances; don't remove/re-add them for upgrades.
Copied studies may inherit IDs; see [discovery](discovery.md) before resetting a copy.

## Configure Python

From the repository folder:

```powershell
uv sync --locked
Copy-Item config.example.json config.local.json
```

Edit `config.local.json`. The example explicitly enables discovery: set `directory`
to your actual Sierra Data/SierraMCPBridge folder. This authorizes all valid present
and future exports there. Without this option, code defaults to allowlist-only.
Discovered source mode stays unknown; do not guess feed delay.

To use a custom path, add a `charts` entry and set the same output path in Sierra:

```json
{
  "id": "primary",
  "chart_number": 1,
  "snapshot_path": "C:/SierraChart/Data/mcp_snapshot.json",
  "source_mode": "unknown",
  "discover_exported_studies": true,
  "studies": []
}
```

Change the illustrative path/chart number. Each writer needs its own file. Explicit
paths work alongside discovery. Relative paths resolve against the config file.

```powershell
uv run --locked sierra-mcp-setup --config config.local.json
```

Preflight is read-only and does not certify public readiness. Its ngrok/OAuth
warnings are not prerequisites for local stdio. Choose a transport in
[connections](connections.md); a local MCP client normally launches stdio itself.

## Verify and upgrade

Call startup context, list charts/studies, then read values/history. Compare symbol,
period, names/colors/settings and a known value with Sierra. Export time is not
proof of fresh market events.

Restart the updated Python reader before loading 1.6; old readers reject it. Use
the dependency-aware manager for [services](service_setup.md). Keep explicit paths;
blank paths use new filenames. Old files are not deleted. Rollback by restoring the
previous exporter and mappings; remove identity pins for legacy exporters.

## Development checks

```powershell
.\scripts\test.ps1
uv run --locked python scripts/export_schemas.py
uv build --no-sources
```

In x64 Visual Studio developer PowerShell:

```powershell
.\scripts\test-native.ps1 -SierraSourceDirectory C:\SierraChart\ACS_Source
```

Native checks build under `runtime` and never install a DLL. Use synthetic fixtures;
never commit real exports or local configuration.
