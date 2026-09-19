# Data and validation limits

Export time is not market-event time. Source mode/delay are operator declarations;
discovered sources default to unknown. Writer liveness is unknown even for recent
files. Closed charts leave exports that become stale. Bid/ask availability, VAP
provenance and volume units are unverified. A Numbers Bars value is an observed
output, not independent aggressor-volume evidence. VWAP is latest-bar VAP-weighted
price, not session VWAP or independently validated market truth.

History is a replaceable window of up to 200,000 loaded bars (configurable per chart via
the exporter's "History bars to export" input; defaults to 1,000), including a forming bar.
Current settings/calculations may repaint past rows. It is not a point-in-time
archive or lossless event stream. Separate calls can see different snapshots.
Chart-local timestamps use Sierra's reported timezone, not assumed UTC.

Metadata describes configured appearance, not rendered pixels. Only selected
subgraphs are accessible. Unsupported/free-text/path inputs are withheld; enums
may remain native codes. Hosting timeframe is not a study's internal timeframe.

## Evidence and open alpha checks

Automated tests cover strict contracts, discovery/identity/bounds, synthetic study
history/metadata, authenticated loopback HTTP, selected auth failures, services and
native Windows writer locking/replacement. One installation has demonstrated
loaded exporter 1.6, actual-chart reads and owner-reported remote two-chart reads
via Entra/ngrok/services. This is not a general certification or security audit.

Remaining validation:

- Independent installation from GitHub on another Windows/Sierra setup.
- Exact comparison against Sierra's values and source-volume fidelity.
- Saved/unsaved, renamed/copied chartbooks, close/reopen and reset behavior.
- Actual simultaneous Sierra writers, sustained performance and crash recovery.
- Full service restart/reboot/logoff, child cleanup, token/secret rotation,
  expiry/refresh/revoke and outage reconnect.
- Broader clients, Python/compiler versions, sources and study types.

Services use fixed names and a single owner/secret store. Multi-user chart isolation,
multiple service instances, Auth0/Cloudflare adapters, account/order tools and
durable storage are not implemented. Services do not open charts.
See the [tester checklist](first_install_test.md).
