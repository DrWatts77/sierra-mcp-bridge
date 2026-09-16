# Third-party software and distribution review

MIT covers this repository's project-owned code/documentation only. No vendor
headers, executable binaries or dependency implementations are vendored in the
source release or bridge wheel. Dependencies are installed by uv under their own
terms; a lockfile does not relicense them.

## External components

- Sierra Chart and ACSIL headers are separately installed vendor software. Users
  build our source against their installation. No Sierra headers/sample files,
  DLLs, chartbooks or market data are included. See [custom-study development](https://www.sierrachart.com/index.php?page=doc/DevelopingCustomStudiesAndSystems.php)
  and [building](https://www.sierrachart.com/index.php?page=doc/HowToBuildAnAdvancedCustomStudyFromSourceCode.html).
- Python, uv, Visual Studio/Windows SDK, ngrok and NSSM are installed separately;
  their own licenses/service terms apply. We make no claim to their trademarks.
- Hatchling 1.29.0 is the build backend, not bundled in our wheel.

## Installed dependency inventory

Recorded from distribution metadata in the locked Windows Python 3.12 environment
on 2026-09-16, including test dependencies. Other platforms can have additional
conditional packages. Declared metadata is not an audit of every embedded native
component. No unknown license metadata appeared here. Before distributing bundled
installers/containers/dependency wheels, review each component and preserve its
licenses/notices; this source-only review does not authorize a bundled release.

| Distribution | Version | Declared license |
| --- | --- | --- |
| aiofile | 3.12.3 | Apache-2.0 |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| attrs | 26.1.0 | MIT |
| Authlib | 1.8.0 | BSD-3-Clause |
| beartype | 0.22.9 | MIT |
| cachetools | 7.1.8 | MIT |
| caio | 0.12.4 | Apache-2.0 |
| cffi | 2.1.1 | MIT-0 |
| click | 8.5.0 | BSD-3-Clause |
| colorama | 0.4.6 | License :: OSI Approved :: BSD License |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause |
| cyclopts | 4.25.2 | Apache-2.0 |
| dnspython | 2.8.0 | ISC |
| docstring_parser | 0.18.0 | MIT |
| email-validator | 2.3.0 | Unlicense |
| exceptiongroup | 1.3.1 | MIT |
| fastmcp | 4.0.3 | Apache-2.0 |
| fastmcp-slim | 4.0.3 | Apache-2.0 |
| griffelib | 2.3.0 | ISC |
| h11 | 0.16.0 | MIT |
| httpcore2 | 2.13.0 | BSD-3-Clause |
| httpx2 | 2.13.0 | BSD-3-Clause |
| idna | 3.19 | BSD-3-Clause |
| iniconfig | 2.3.0 | MIT |
| jaraco.classes | 3.4.0 | MIT |
| jaraco.context | 6.1.2 | MIT |
| jaraco.functools | 4.6.0 | MIT |
| joserfc | 1.7.5 | BSD-3-Clause |
| jsonref | 1.1.0 | MIT |
| jsonschema | 4.26.0 | MIT |
| jsonschema-path | 0.5.0 | Apache-2.0 |
| jsonschema-specifications | 2025.9.1 | MIT |
| keyring | 25.7.0 | MIT |
| markdown-it-py | 4.2.0 | MIT |
| mcp | 2.2.0 | MIT |
| mcp-types | 2.2.0 | MIT |
| mdurl | 0.1.2 | MIT |
| more-itertools | 11.1.0 | MIT |
| openapi-pydantic | 0.5.1 | MIT |
| opentelemetry-api | 1.44.0 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pathable | 0.6.0 | Apache-2.0 |
| platformdirs | 4.11.8 | MIT |
| pluggy | 1.6.0 | MIT |
| py-key-value-aio | 0.4.5 | Apache-2.0 |
| pycparser | 3.0 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| pydantic-settings | 2.15.0 | MIT |
| pydantic_core | 2.46.5 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| PyJWT | 2.14.0 | MIT |
| pyperclip | 1.11.0 | BSD |
| pytest | 8.4.2 | MIT |
| python-dotenv | 1.2.3 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| pywin32 | 312 | PSF |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |
| referencing | 0.37.0 | MIT |
| rich | 15.0.0 | MIT |
| rich-rst | 2.1.0 | MIT |
| rpds-py | 2026.6.3 | MIT |
| sse-starlette | 3.4.11 | BSD-3-Clause |
| starlette | 1.6.0 | BSD-3-Clause |
| truststore | 0.10.4 | MIT |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| uncalled-for | 0.4.0 | MIT |
| uvicorn | 0.53.0 | BSD-3-Clause |
| watchfiles | 1.2.0 | MIT |
| websockets | 17.1 | BSD-3-Clause |

[MIT license](https://opensource.org/license/mit); [Apache dependency terms](https://www.apache.org/licenses/LICENSE-2.0.html). Exact dependency license files ship with their distributions.

## Conditional and build dependencies

The lockfile also contains conditional packages not installed on the tested Windows
host. Exact-version PyPI metadata reports httpx2-jsfetch 1.0 as BSD-3-Clause,
jeepney 0.9.0 as MIT, and SecretStorage 3.5.0 as BSD-3-Clause. These paths were not
runtime-tested here. The Hatch project declares MIT in its
[upstream license](https://github.com/pypa/hatch/blob/master/LICENSE.txt); Hatchling
1.29.0 is used only as a build dependency. This does not grant a license to optional
vendor software or third-party compiled bundles.
