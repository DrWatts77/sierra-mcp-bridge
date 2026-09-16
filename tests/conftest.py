import json
import time
from pathlib import Path

import pytest

from sierra_mcp_bridge.config import BridgeConfig, ChartConfig, StudyConfig


@pytest.fixture
def raw():
    data = json.loads((Path(__file__).parent / "fixtures/snapshot.json").read_text())
    data["snapshot_time_unix_ms"] = int(time.time() * 1000)
    return data


@pytest.fixture
def setup_bridge(tmp_path, raw):
    first = tmp_path / "first.json"
    first.write_text(json.dumps(raw))
    second = tmp_path / "second.json"
    second_raw = {**raw, "chart_number": 2, "last_price": 201.5, "studies": []}
    second.write_text(json.dumps(second_raw))
    studies = [StudyConfig(key="ema", label="Synthetic EMA", study_id=2, subgraph_index=0)]
    config = BridgeConfig(charts=[
        ChartConfig(id="first", chart_number=1, snapshot_path=str(first), source_mode="delayed",
                    expected_delay_seconds=600, studies=studies),
        ChartConfig(id="second", chart_number=2, snapshot_path=str(second), source_mode="synthetic", studies=studies),
    ])
    return config, first, second
