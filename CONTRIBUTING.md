# Contributing

This repository contains the reusable read-only bridge, its exporter, synthetic
tests and user setup documentation. Keep changes within that product boundary.

Use Python 3.12 or later within the declared supported range. Run
`uv sync --locked`, `scripts/test.ps1` and `uv build --no-sources`. Regenerate
schemas with `uv run --locked python scripts/export_schemas.py` after model changes.
Native checks use `scripts/test-native.ps1` from an x64 Visual Studio developer
PowerShell with your installed Sierra ACS_Source directory. No Sierra headers
or compiled DLLs belong in a contribution.

New public files must be added deliberately to the exact path allowlists in
`.gitignore` and the source-distribution configuration in `pyproject.toml`.
Keep credentials, real exports, local configs, service/OAuth state and runtime
artifacts out of Git. Contributions are licensed under this project's MIT license.

Describe the problem, resulting behavior and validation. Distinguish synthetic
tests, actual Sierra observations and authenticated remote-client tests. Preserve
unavailable values and quality warnings. Tests must use synthetic fixtures.

See [first installation feedback](docs/first_install_test.md) for tester guidance.
