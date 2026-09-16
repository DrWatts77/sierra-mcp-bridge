import json
import time
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from sierra_mcp_bridge.config import BridgeConfig, load_config
from sierra_mcp_bridge.reader import SnapshotReader


def test_delayed_is_not_stale_and_freshness_is_unknown(setup_bridge):
    config, *_ = setup_bridge
    result = SnapshotReader(config).read("first")
    assert result.status == "degraded"
    assert result.quality.expected_delay_seconds == 600
    assert result.quality.market_event_age_seconds is None
    assert result.quality.market_freshness == "unknown"


@pytest.mark.parametrize("change,warning", [
    ({"schema_version": 2}, "unsupported_schema"),
    ({"schema_version": True}, "unsupported_schema"),
    ({"chart_number": 2}, "chart_identity_mismatch"),
    ({"last_price": float("nan")}, "invalid_snapshot"),
    ({"volume": -1}, "invalid_snapshot"),
    ({"last_price": "100"}, "invalid_snapshot"),
    ({"snapshot_time_unix_ms": 9999999999999}, "export_clock_in_future"),
    ({"studies": [{"study_id": 2, "subgraph_index": 0, "value": None, "reason": None}]}, "invalid_snapshot"),
])
def test_invalid_data(setup_bridge, raw, change, warning):
    config, path, _ = setup_bridge
    path.write_text(json.dumps({**raw, **change}))
    result = SnapshotReader(config).read("first")
    assert result.status == "invalid" and result.data is None
    assert warning in result.warnings


@pytest.mark.parametrize("content", ["", "{", "[]", '{"schema_version":1,"schema_version":2}', "[" * 1500])
def test_bad_json(setup_bridge, content):
    config, path, _ = setup_bridge
    path.write_text(content)
    assert SnapshotReader(config).read("first").status == "invalid"


def test_missing_locked_oversized_and_no_cached_fallback(setup_bridge):
    config, path, _ = setup_bridge
    reader = SnapshotReader(config)
    assert reader.read("first").data
    with patch("pathlib.Path.open", side_effect=PermissionError):
        assert reader.read("first").warnings == ["snapshot_read_failed"]
    path.write_bytes(b" " * (config.max_snapshot_bytes + 1))
    assert reader.read("first").warnings == ["snapshot_too_large"]
    path.unlink()
    assert reader.read("first").data is None
    assert reader.read("first").warnings == ["snapshot_missing"]
    assert reader.read("not_allowed").warnings == ["chart_not_configured"]


def test_stale_export_and_old_schema(setup_bridge, raw):
    config, path, _ = setup_bridge
    raw.pop("studies")
    raw.pop("exporter_revision")
    raw.pop("bar_period")
    raw["snapshot_time_unix_ms"] = int((time.time() - 200) * 1000)
    path.write_text(json.dumps(raw))
    result = SnapshotReader(config).read("first")
    assert result.status == "stale"
    assert result.data.studies == []
    assert result.timeframe is None
    assert "chart_timeframe_unavailable_rebuild_exporter" in result.warnings


def test_config_portability_and_duplicate_rejection(setup_bridge, tmp_path):
    config, _, _ = setup_bridge
    data = config.model_dump()
    data["charts"][0]["snapshot_path"] = "first.json"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    loaded = load_config(path)
    assert loaded.charts[0].snapshot_path == str(tmp_path / "first.json")
    data["charts"][1]["snapshot_path"] = "first.json"
    with pytest.raises(ValidationError):
        BridgeConfig.model_validate(data)


def test_atomic_replacement_does_not_mix_charts(setup_bridge, raw):
    config, path, _ = setup_bridge
    reader = SnapshotReader(config)
    for number in range(30):
        replacement = path.with_suffix(".tmp")
        replacement.write_text(json.dumps({**raw, "last_price": float(number)}))
        replacement.replace(path)
        assert reader.read("first").data.last_price == number
        assert reader.read("second").data.last_price == 201.5
