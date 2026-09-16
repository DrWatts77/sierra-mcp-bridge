# Chart discovery and upgrade

Discovery is an optional owner-controlled directory permission. Enabling it authorizes all valid present and future revision 1.6 exports in that directory to the bridge's authenticated clients. It does not expose arbitrary tool-supplied paths or scan the Sierra installation. Keep authentication configured as before.

## Configuration

Keep existing explicit `charts` mappings and add:

```json
"discovery": {
  "enabled": true,
  "directory": "C:/SierraChart/Data/SierraMCPBridge",
  "max_files": 64,
  "max_directory_entries": 512,
  "max_total_bytes": 16000000,
  "export_stale_after_seconds": 120
}
```

The path is illustrative; choose your installation's Data/SierraMCPBridge folder. Relative paths resolve against the configuration file. Discovery is disabled when absent or when `enabled` is false. An empty `charts` list is permitted only with discovery enabled. Server configuration changes require a bridge restart; adding/removing exports in an already authorized directory does not.

The existing explicit chart alias and its custom path remain valid. Each tool call takes a new bounded inventory, with one snapshot read per file for that call. Discovered IDs are `export_<32-character export_id>`; symbol and timeframe are descriptive metadata and may change without changing the ID. Discovered charts use source mode `unknown`, no declared feed delay, unverified VAP/bid-ask quality and unknown market freshness. Use an explicit mapping to declare a chart-specific delayed/live/replay source mode.

## Reconciliation and diagnostics

Only immediate `mcp_*.json` files are candidates. Each must satisfy the full schema and revision 1.6 identity contract. Nested directories, unrelated filenames and lock/temp files are not read. Explicit mappings own their canonical path, even when their chart-number/identity check fails; discovery never bypasses them. A separate file carrying the same export ID is a conflict: all associated chart reads return invalid without market data. Stale duplicates also conflict; the bridge does not guess which copy is authoritative. A discovered logical ID colliding with an explicit alias is invalid. Intentional copies need their own identity reset in Sierra.

`get_startup_context.discovery_warnings` reports counts by diagnostic code, without filesystem paths or rejected file contents. `list_charts` includes each chart's origin, symbol, timeframe, read status and warnings. Invalid discovery candidates are omitted with aggregate diagnostics. Missing directories produce a diagnostic and preserve explicit mappings. Entry/file/aggregate-byte overflow rejects the entire discovered batch for that call while explicit mappings remain available. Limits count immediate entries (including lock files), candidate files, and bytes actually read; each file also has the existing `max_snapshot_bytes` limit. Archive/remove obsolete files only as an explicit operator maintenance action; the bridge never deletes them.

Symlinks, junction roots/ancestors and non-regular/hard-linked candidate files are rejected. Windows reads verify the opened file handle's final parent before reading bytes, to reject a redirected path even if it changed after enumeration. The boundary is against accidental or tool-directed traversal, not a hostile local administrator who can modify the service/configuration itself. Windows is the supported host; the non-Windows handle check requires `/proc/self/fd` and otherwise fails closed.

Removing an export removes the discovered chart on the next call. Reopening it with its saved identity restores the same ID. Closing Sierra may leave a complete snapshot: it remains listed and becomes `stale` once its export timestamp exceeds the configured threshold. Writer liveness is always reported as unknown, never active. A newly closed chart may look recently exported until that threshold; export age cannot establish that a chart is open or that markets are fresh. Stale data stays explicitly marked in reads. No success cache masks current failures.

## Deployment order and human actions

1. Update the Python package/configuration and restart the service pair with `Manage-SierraMCPService.ps1 -Action restart`. The installed tunnel depends on the bridge, so the manager stops the tunnel first and starts it again after the bridge. Old readers reject revision 1.6 snapshots.
2. Rebuild/reload `sierra_mcp_bridge.cpp` using Sierra's existing custom-study build workflow. Do not add duplicate bridge studies or replace chartbooks. One DLL rebuild updates the existing instances when Sierra reloads it.
3. Keep an existing primary custom path if desired. On additional charts, leave **Snapshot output path** blank to use Data/SierraMCPBridge automatically. Keep the intended study/subgraph selections. Newly added instances get independent IDs; use the one-time reset only for intentional copies with inherited IDs.
4. Save the chartbook after identity generation/reset. Check Sierra's Message Log for claimed-path or writer errors.
5. Call `get_startup_context`, `list_charts`, then each chart's `list_studies`, values and history through the authenticated client. Check symbol, timeframe, study names/colors and values independently against Sierra.

Rollback: disable discovery and restore previous explicit paths before loading the previous exporter. Remove configured identity pins if reverting to an exporter without identity. New Python readers accept old snapshots. No migration deletes old exports; an old file is not proof of a current writer.

Synthetic tests cover discovery/refresh, strict validation and limits, identity/path conflicts, Windows boundary checks, and real loopback authenticated HTTP reads for two charts with matching chart numbers and different studies/timeframes. Native exporter tests cover identity persistence bytes and Windows locking/replacement. Actual Sierra save/reload, copied/renamed chartbooks, two live exports and remote authenticated-client acceptance remain separate deployment checks.
