# First installation feedback

This alpha has worked on one Windows/Sierra installation. A clean directory and
virtual environment test on that same host is not a clean-machine certification.
The next validation is an independent tester installing from a GitHub checkout.

Record Windows, Sierra, Python, uv and compiler versions. Start with the
[installation guide](installation.md), then [connections](connections.md).

1. Clone into a new directory outside Sierra's Data folder; run `uv sync --locked`.
2. Build the supplied ACSIL source using the tester's installed Sierra headers.
3. Add one bridge instance to each of two charts, select outputs, leave paths
   blank, enable discovery for the tester's directory, and save the chartbook.
4. Check `get_startup_context`, chart symbols/timeframes, names/colors/settings,
   values and recent history. Compare a known bar/value directly with Sierra.
5. Test explicit custom-path compatibility and unknown/stale/missing data.
6. Set up the tester's own Entra registration and ngrok account/domain. Confirm
   public unauthorized requests are denied, then perform authenticated reads.
7. Only after manual startup works, optionally install Windows services and test
   enable, restart, stop, logoff/reboot and Sierra close/reopen behavior.

For each failure, record the exact step, expected/actual result and a redacted
error. Never attach private configs, account/trade records, chartbooks, market
exports, token-bearing URLs, OAuth caches, passwords or client secrets. Screenshots
should conceal accounts and private endpoints. Use synthetic minimal examples.

Update the relevant guide and add a regression test when a repeatable defect is
found. Track machine-specific limitations separately from general bugs. Do not
mark a scenario passed merely because the service says Running.
