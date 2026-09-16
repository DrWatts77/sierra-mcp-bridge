import asyncio
import copy
import json
import secrets
import socket
from datetime import datetime, timedelta

import pytest
from fastmcp import Client

from sierra_mcp_bridge.reader import SnapshotReader
from sierra_mcp_bridge.server import create_server
from test_mcp import http_process


def add_history(raw, count=200):
    raw = copy.deepcopy(raw)
    raw.update(exporter_revision="1.3", chart_timezone="UTC", bar_index=count - 1)
    history = []
    for i in range(count):
        studies = copy.deepcopy(raw["studies"])
        if i != count - 1:
            studies[0]["value"] = float(i)
        history.append(dict(bar_index=i, bar_start_sc_datetime=raw["bar_start_sc_datetime"] - (count-1-i)/1440,
                            bar_start_chart_time=(datetime(2026, 9, 14, 12) + timedelta(minutes=i)).isoformat(timespec="microseconds"),
                            is_closed=i < count - 1, open=100.0, high=101.0, low=99.0, close=100.25,
                            volume=20.0, studies=studies))
    raw["history"] = history
    return raw


def test_history_http(setup_bridge, raw, tmp_path):
    config, path, _ = setup_bridge
    path.write_text(json.dumps(add_history(raw)))
    token = secrets.token_urlsafe(32)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    async def check(url):
        async with Client(url, auth=token, mode="legacy") as client:
            result = await client.call_tool("get_study_history", {"chart_id": "first", "study_key": "ema"})
            data = result.structured_content
            assert data["timeframe"]["seconds_per_bar"] == 60
            assert data["data"]["returned_bars"] == 200
            assert data["data"]["bars"][0]["bar_index"] == 0
            assert data["data"]["bars"][-1]["value"] == 99.875
            assert data["data"]["chart_timezone"] == "UTC"
            assert data["data"]["includes_forming_bar"]
            assert "studies" not in data["data"]["bars"][0]  # only requested mapping returned
            for args in [dict(limit=201), dict(limit=0), dict(study_key="unlisted")]:
                request = {"chart_id": "first", "study_key": "ema", **args}
                response = await client.call_tool("get_study_history", request, raise_on_error=False)
                if "limit" in args:
                    assert response.is_error
                else:
                    assert response.structured_content["status"] == "unavailable"
            response = await client.call_tool("get_study_history", {"chart_id": "first", "study_key": "ema", "closed_only": True})
            assert response.structured_content["data"]["returned_bars"] == 199
            assert not response.structured_content["data"]["includes_forming_bar"]
    with http_process(config, tmp_path, token, port) as url:
        asyncio.run(check(url))


@pytest.mark.parametrize("count", [1, 10, 200])
def test_history_short_loaded_chart_and_tail(setup_bridge, raw, count):
    config, path, _ = setup_bridge
    path.write_text(json.dumps(add_history(raw, count)))

    async def check():
        async with Client(create_server(config)) as client:
            result = await client.call_tool("get_study_history", {"chart_id": "first", "study_key": "ema", "limit": 5})
            data = result.structured_content["data"]
            assert data["returned_bars"] == min(count, 5)
            assert data["bars"][-1]["bar_index"] == count - 1
            assert data["bars"][0]["bar_index"] == max(0, count - 5)
    asyncio.run(check())


@pytest.mark.parametrize("fault", ["oversized", "reordered", "duplicate", "latest_mismatch", "missing", "closure"])
def test_history_integrity(setup_bridge, raw, fault):
    config, path, _ = setup_bridge
    raw = add_history(raw)
    if fault == "oversized":
        raw["history"].append(raw["history"][-1])
    elif fault == "reordered":
        raw["history"].reverse()
    elif fault == "duplicate":
        raw["history"][0]["studies"].append(raw["history"][0]["studies"][0])
    elif fault == "latest_mismatch":
        raw["history"][-1]["studies"][0]["value"] = 123.0
    elif fault == "closure":
        raw["history"][-1]["is_closed"] = True
    else:
        raw.pop("history")
    path.write_text(json.dumps(raw))
    assert SnapshotReader(config).read("first").status == "invalid"


def test_history_missing_values_and_legacy(setup_bridge, raw):
    config, path, _ = setup_bridge

    async def check():
        async with Client(create_server(config)) as client:
            response = await client.call_tool("get_study_history", {"chart_id": "first", "study_key": "ema"})
            assert response.structured_content["status"] == "unavailable"
            assert "history_unavailable_rebuild_exporter" in response.structured_content["warnings"]
            data = add_history(raw)
            data["history"][0]["studies"][0].update(value=None, reason="study_unavailable")
            path.write_text(json.dumps(data))
            response = await client.call_tool("get_study_history", {"chart_id": "first", "study_key": "ema"})
            assert response.structured_content["data"]["bars"][0]["value"] is None
            assert "study_history_partially_unavailable" in response.structured_content["warnings"]
    asyncio.run(check())
