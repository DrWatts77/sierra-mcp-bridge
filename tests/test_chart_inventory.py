import asyncio
import json
import os
import secrets
import socket
from pathlib import Path
from unittest.mock import patch

import pytest
from fastmcp import Client
from pydantic import ValidationError

from sierra_mcp_bridge.chart_inventory import ChartInventory, bounded_content
from sierra_mcp_bridge.config import BridgeConfig, ChartConfig, DiscoveryConfig, load_config
from sierra_mcp_bridge.server import create_server
from test_history import add_history
from test_mcp import http_process
from test_metadata_guidance import metadata


def publish(folder, raw, identity="a" * 32, name=None, price=100.25, period=60):
    snapshot = add_history(raw, 3)
    snapshot.update(exporter_revision="1.6", export_id=identity, last_price=price)
    snapshot["bar_period"]["parameters"][0] = period
    snapshot["studies"][0]["study_name"] = "Study " + identity[0]
    snapshot["studies"][0]["metadata"] = metadata()
    snapshot["studies"][0]["metadata"]["primary_color"] = "#ffffff" if identity[0] == "a" else "#0000ff"
    snapshot["studies"][0]["value"] = price
    snapshot["history"][-1]["studies"][0]["value"] = price
    path = folder / (name or f"mcp_{identity}.json")
    path.write_text(json.dumps(snapshot))
    return path


@pytest.fixture
def discovery_config(tmp_path):
    folder = tmp_path / "exports"
    folder.mkdir()
    return BridgeConfig(discovery=DiscoveryConfig(enabled=True, directory=str(folder)))


def test_opt_in_and_relative_directory(setup_bridge, tmp_path, raw):
    config, *_ = setup_bridge
    publish(tmp_path, raw)
    config.discovery = DiscoveryConfig(directory=str(tmp_path))
    assert set(ChartInventory(config).charts) == {"first", "second"}
    with pytest.raises(ValidationError):
        BridgeConfig(charts=[])
    path = tmp_path / "config.json"
    data = config.model_dump()
    data["discovery"]["directory"] = "exports"
    path.write_text(json.dumps(data))
    assert load_config(path).discovery.directory == str(tmp_path / "exports")


def test_add_remove_reopen_and_stale(discovery_config, raw):
    root = Path(discovery_config.discovery.directory)
    assert not ChartInventory(discovery_config).charts
    path = publish(root, raw)
    key = "export_" + "a" * 32
    current = ChartInventory(discovery_config)
    assert current.read(key).data.export_id == "a" * 32
    assert current.read(key).quality.source_mode == "unknown"
    assert current.read(key).quality.market_freshness == "unknown"
    stale = ChartInventory(discovery_config, clock=lambda: raw["snapshot_time_unix_ms"] / 1000 + 121)
    assert stale.read(key).status == "stale"
    assert "writer_liveness_unknown" in stale.read(key).warnings
    path.unlink()
    assert ChartInventory(discovery_config).read(key).status == "unavailable"
    publish(root, raw)
    assert ChartInventory(discovery_config).read(key).data


def test_explicit_path_precedence_and_identity_conflicts(discovery_config, raw):
    root = Path(discovery_config.discovery.directory)
    path = publish(root, raw)
    discovery_config.charts = [ChartConfig(id="primary", chart_number=1, snapshot_path=str(path), source_mode="delayed")]
    inventory = ChartInventory(discovery_config)
    assert list(inventory.charts) == ["primary"]
    assert inventory.read("primary").quality.source_mode == "delayed"
    publish(root, raw, name="mcp_copy.json")
    conflict = ChartInventory(discovery_config)
    assert conflict.read("primary").warnings == ["duplicate_export_identity"]
    assert conflict.read("export_" + "a" * 32).data is None
    # An invalid explicit mapping cannot be bypassed by path discovery.
    (root / "mcp_copy.json").unlink()
    discovery_config.charts[0].chart_number = 2
    invalid = ChartInventory(discovery_config)
    assert list(invalid.charts) == ["primary"]
    assert invalid.read("primary").warnings == ["chart_identity_mismatch"]


def test_duplicate_discovered_identity_and_logical_id_collision(discovery_config, raw, tmp_path):
    root = Path(discovery_config.discovery.directory)
    publish(root, raw)
    publish(root, raw, name="mcp_duplicate.json")
    inventory = ChartInventory(discovery_config)
    assert len(inventory.charts) == 1
    assert inventory.read("export_" + "a" * 32).warnings == ["duplicate_export_identity"]
    (root / "mcp_duplicate.json").unlink()
    explicit = publish(tmp_path, raw, identity="b" * 32)
    discovery_config.charts = [ChartConfig(id="export_" + "a" * 32, chart_number=1, snapshot_path=str(explicit))]
    assert ChartInventory(discovery_config).read("export_" + "a" * 32).warnings == ["chart_id_conflict"]


@pytest.mark.parametrize("fault,warning", [
    ("malformed", "discovery_invalid_snapshot"),
    ("duplicate_keys", "discovery_invalid_snapshot"),
    ("legacy", "discovery_identity_revision_required"),
    ("schema", "discovery_invalid_snapshot"),
    ("bool_schema", "discovery_invalid_snapshot"),
    ("oversized", "discovery_snapshot_too_large"),
])
def test_reject_bad_exports(discovery_config, raw, fault, warning):
    root = Path(discovery_config.discovery.directory)
    path = publish(root, raw)
    data = json.loads(path.read_text())
    if fault == "malformed":
        path.write_text("{")
    elif fault == "duplicate_keys":
        path.write_text('{"schema_version":1,"schema_version":1}')
    elif fault == "oversized":
        path.write_bytes(b" " * (discovery_config.max_snapshot_bytes + 1))
    else:
        if fault == "legacy": data["exporter_revision"] = "1.5"
        if fault == "schema": data["schema_version"] = 2
        if fault == "bool_schema": data["schema_version"] = True
        path.write_text(json.dumps(data))
    inventory = ChartInventory(discovery_config)
    assert not inventory.charts
    assert inventory.warnings[warning] == 1


@pytest.mark.parametrize("limit,warning", [
    ("max_files", "discovery_file_limit"),
    ("max_directory_entries", "discovery_directory_entry_limit"),
    ("max_total_bytes", "discovery_total_byte_limit"),
])
def test_bounds_fail_entire_discovered_batch(discovery_config, raw, tmp_path, limit, warning):
    root = Path(discovery_config.discovery.directory)
    publish(root, raw)
    publish(root, raw, "b" * 32)
    setattr(discovery_config.discovery, limit, 1024 if limit == "max_total_bytes" else 1)
    explicit = publish(tmp_path, raw, "c" * 32)
    discovery_config.charts = [ChartConfig(id="primary", chart_number=1, snapshot_path=str(explicit))]
    inventory = ChartInventory(discovery_config)
    assert list(inventory.charts) == ["primary"]
    assert inventory.read("primary").data
    assert inventory.warnings[warning] == 1


def test_no_recursion_or_unrelated_reads(discovery_config, raw):
    root = Path(discovery_config.discovery.directory)
    nested = root / "nested"
    nested.mkdir()
    publish(nested, raw)
    (root / "secrets.json").write_text("not an export")
    inventory = ChartInventory(discovery_config)
    assert not inventory.charts
    assert not inventory.warnings


def test_opened_handle_escape_rejected_before_read(discovery_config, raw, tmp_path):
    root = Path(discovery_config.discovery.directory)
    path = publish(root, raw)
    with patch("sierra_mcp_bridge.chart_inventory.opened_path", return_value=tmp_path / "outside.json"):
        with pytest.raises(OSError):
            bounded_content(path, root, 2000000)
    external = publish(tmp_path, raw, "b" * 32)
    link = root / "mcp_hardlink.json"
    os.link(external, link)
    inventory = ChartInventory(discovery_config)
    assert inventory.warnings["discovery_boundary_or_read_failed"] == 1
    assert len(inventory.charts) == 1


def test_junction_root_rejected(discovery_config, raw, tmp_path):
    if os.name != "nt":
        pytest.skip("Windows junction test")
    import subprocess
    root = Path(discovery_config.discovery.directory)
    external = tmp_path / "external"
    external.mkdir()
    publish(external, raw)
    junction = root / "linked"
    result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(external)], capture_output=True)
    assert result.returncode == 0
    try:
        discovery_config.discovery.directory = str(junction)
        inventory = ChartInventory(discovery_config)
        assert not inventory.charts
        assert inventory.warnings["discovery_directory_unavailable"] == 1
    finally:
        junction.rmdir()  # Remove only the test junction itself, never its target tree.


def test_mcp_refresh_separation_and_http(discovery_config, raw, tmp_path):
    root = Path(discovery_config.discovery.directory)
    publish(root, raw, price=111.0, period=60)
    token = secrets.token_urlsafe(32)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    async def check(url):
        async with Client(url, auth=token, mode="legacy") as client:
            a, b = "export_" + "a" * 32, "export_" + "b" * 32
            before = await client.call_tool("get_startup_context")
            assert len(before.structured_content["charts"]) == 1
            second = publish(root, raw, "b" * 32, price=222.0, period=120)
            for key, value, seconds in [(a, 111.0, 60), (b, 222.0, 120)]:
                response = await client.call_tool("get_study_values", {"chart_id": key, "study_key": "id2_sg1"})
                result = response.structured_content
                assert result["data"]["value"] == value
                assert result["timeframe"]["seconds_per_bar"] == seconds
                assert result["quality"]["source_mode"] == "unknown"
                assert result["data"]["study_name"] == "Study " + key[-1]
                assert result["data"]["metadata"]["primary_color"] == ("#ffffff" if key == a else "#0000ff")
                history = await client.call_tool("get_study_history", {"chart_id": key, "study_key": "id2_sg1"})
                assert history.structured_content["data"]["bars"][-1]["value"] == value
                assert str(root) not in json.dumps(result)
            after = await client.call_tool("get_startup_context")
            assert len(after.structured_content["charts"]) == 2
            listing = await client.call_tool("list_charts")
            listed = listing.structured_content["result"]
            assert len(listed) == 2
            assert all(c["writer_liveness"] == "unknown" and c["origin"] == "discovered" for c in listed)
            assert {c["timeframe"]["seconds_per_bar"] for c in listed} == {60, 120}
            second.unlink()
            missing = await client.call_tool("get_snapshot", {"chart_id": b})
            assert missing.structured_content["status"] == "unavailable"
            (root / "mcp_broken.json").write_text("{")
            diagnostic = await client.call_tool("get_startup_context")
            assert diagnostic.structured_content["discovery_warnings"] == {"discovery_invalid_snapshot": 1}

    with http_process(discovery_config, tmp_path, token, port) as url:
        asyncio.run(check(url))
    # A new server process rediscovers the same saved ID without a manifest/cache.
    async def restart_check(url):
        async with Client(url, auth=token, mode="legacy") as client:
            result = await client.call_tool("get_snapshot", {"chart_id": "export_" + "a" * 32})
            assert result.structured_content["data"]["last_price"] == 111.0
    with http_process(discovery_config, tmp_path, token, port) as url:
        asyncio.run(restart_check(url))
