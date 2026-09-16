# Sierra MCP Bridge

Read selected Sierra Chart study outputs from MCP clients. The bridge runs beside
Sierra and offers eight read-only tools over Streamable HTTP or local stdio.
It does not call a model API and needs no LLM API key.

**Status: 0.1.0 alpha.** One Windows/Sierra installation has demonstrated Entra
OAuth, ngrok HTTPS, Windows services and authenticated ChatGPT reads across two
charts. Independent installation and broader lifecycle validation are ongoing.

## Features

- Optional bounded chart discovery, saved exporter IDs and explicit paths.
- Chart symbol/timeframe and selected study names, settings, colors and values.
- Up to 200 loaded bars of history, with forming-bar status and quality warnings.
- Microsoft Entra OAuth, optional ngrok exposure and optional NSSM services.

Tools: `get_startup_context`, `list_charts`, `list_studies`, `get_snapshot`,
`get_study_values`, `get_study_history`, `get_footprint`, `get_data_health`.

## Start here

1. Follow [installation](docs/installation.md).
2. Choose [connections and authentication](docs/connections.md).
3. Optionally configure [Windows services](docs/service_setup.md) after manual startup works.
4. Review [data and validation limits](docs/limitations.md).

New testers: [first-install checklist](docs/first_install_test.md).
Development: [contributing](CONTRIBUTING.md).

No account reads, order execution or persistent historical database are included.
Public source code does not make a private installation anonymously accessible.

## License

Project-owned code and documentation are MIT licensed; see [LICENSE](LICENSE).
External software/services retain their terms; see [third-party review](THIRD_PARTY.md).
Sierra Chart is not affiliated with or an endorser of this project.
