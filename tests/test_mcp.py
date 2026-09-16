import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager

from fastmcp import Client
import pytest

from sierra_mcp_bridge.server import create_server


def test_tools_and_bounds(setup_bridge):
    config, _, _ = setup_bridge

    async def check():
        async with Client(create_server(config)) as client:
            tools = await client.list_tools()
            assert len(tools) == 8
            assert all(tool.output_schema for tool in tools)
            assert all(tool.annotations.read_only_hint for tool in tools)
            result = await client.call_tool("get_snapshot", {"chart_id": "first"})
            assert result.structured_content["data"]["last_price"] == 100.25
            assert "snapshot_path" not in str(result.structured_content)
            result = await client.call_tool("get_footprint", {"chart_id": "first", "limit": 1})
            assert result.structured_content["data"]["next_offset"] == 1
            assert result.structured_content["data"]["levels"][0]["delta"] is None
            for args in [{"chart_id": "first", "limit": 201}, {"chart_id": "../private"},
                         {"chart_id": "first", "offset": -1}]:
                result = await client.call_tool("get_footprint", args, raise_on_error=False)
                assert result.is_error
            result = await client.call_tool("get_study_values", {"chart_id": "second", "study_key": "ema"})
            assert result.structured_content["status"] == "unavailable"
            assert result.structured_content["data"]["value"] is None
            result = await client.call_tool("get_study_values", {"chart_id": "first", "study_key": "unlisted"})
            assert result.structured_content["warnings"] == ["study_not_configured"]
    asyncio.run(check())


@contextmanager
def http_process(config, tmp_path, token, port, auth_profile="development"):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config.model_dump()))
    env = {**os.environ, "SIERRA_MCP_TOKEN": token, "FASTMCP_CHECK_FOR_UPDATES": "off"}
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen([sys.executable, "-m", "sierra_mcp_bridge.server", "--config", str(path),
                                    "--port", str(port), "--auth", auth_profile], env=env, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail("Server exited; inspect test server.log")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail("Server startup timed out")
            yield f"http://127.0.0.1:{port}/mcp"
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.mark.parametrize("mode", ["legacy", "auto"])
def test_real_streamable_http_auth_calls_and_restart(setup_bridge, tmp_path, mode):
    config, _, second = setup_bridge
    token = secrets.token_urlsafe(32)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    async def check(url):
        async with Client(url, auth=token, mode=mode) as client:
            assert client.server_info is not None
            if mode == "legacy":
                assert client.initialize_result is not None
            assert len(await client.list_tools()) == 8
            result = await client.call_tool("get_study_values", {"chart_id": "first", "study_key": "ema"})
            assert result.structured_content["data"]["value"] == 99.875
            assert result.structured_content["timeframe"]["label"] == "1 minute"
            assert result.structured_content["timeframe"]["seconds_per_bar"] == 60
            assert result.structured_content["quality"]["source_mode"] == "delayed"
            result = await client.call_tool("get_snapshot", {"chart_id": "second"})
            assert result.structured_content["data"]["last_price"] == 201.5
            original = second.read_bytes()
            try:
                second.write_text("{bad")
                result = await client.call_tool("get_snapshot", {"chart_id": "second"})
                assert result.structured_content["status"] == "invalid" and result.structured_content["data"] is None
            finally:
                second.write_bytes(original)

    for _ in range(2):
        with http_process(config, tmp_path, token, port) as url:
            for bad_token in [None, "wrong-token"]:
                headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
                if bad_token:
                    headers["Authorization"] = "Bearer " + bad_token
                request = urllib.request.Request(url, data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}', headers=headers)
                with pytest.raises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request, timeout=5)
                assert error.value.code == 401
            asyncio.run(check(url))


def test_explicit_anonymous_http_with_existing_token(setup_bridge, tmp_path):
    config, _, _ = setup_bridge
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    async def check(url):
        async with Client(url) as client:
            assert len(await client.list_tools()) == 8
            result = await client.call_tool('get_snapshot', {'chart_id': 'first'})
            assert result.structured_content['data']['last_price'] == 100.25
    with http_process(config, tmp_path, 'existing-token-must-not-enable-auth', port, 'none') as url:
        asyncio.run(check(url))


def test_real_local_stdio_without_http(setup_bridge, tmp_path):
    from fastmcp.client.transports import StdioTransport
    config, _, _ = setup_bridge
    path = tmp_path / 'stdio.json'
    path.write_text(json.dumps(config.model_dump()))
    async def check():
        transport = StdioTransport(command=sys.executable,
            args=['-m', 'sierra_mcp_bridge.server', '--config', str(path), '--transport', 'stdio', '--auth', 'none'],
            keep_alive=False)
        async with Client(transport) as client:
            assert len(await client.list_tools()) == 8
            result = await client.call_tool('get_study_values', {'chart_id': 'first', 'study_key': 'ema'})
            assert result.structured_content['data']['value'] == 99.875
    asyncio.run(check())


def test_default_http_still_requires_token(tmp_path):
    env = dict(os.environ)
    env.pop('SIERRA_MCP_TOKEN', None)
    result = subprocess.run([sys.executable, '-m', 'sierra_mcp_bridge.server', '--config', str(tmp_path / 'unused.json')],
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert 'HTTP requires SIERRA_MCP_TOKEN' in result.stderr
