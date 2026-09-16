import asyncio
import json

import pytest
from fastmcp import Client

from sierra_mcp_bridge.reader import SnapshotReader
from sierra_mcp_bridge.server import create_server
from sierra_mcp_bridge.timeframe import BarPeriod, describe_period


@pytest.mark.parametrize("seconds,label", [(1, "1 second"), (30, "30 seconds"), (60, "1 minute"),
                                          (300, "5 minutes"), (3600, "1 hour"), (90, "90 seconds")])
def test_time_periods(raw, seconds, label):
    raw["bar_period"]["parameters"][0] = seconds
    result = describe_period(BarPeriod.model_validate(raw["bar_period"]))
    assert result.label == label
    assert result.seconds_per_bar == seconds


@pytest.mark.parametrize("kind,days,label", [(1, 1, "1 day"), (1, 3, "3 days"), (2, 0, "Weekly"),
                                          (3, 0, "Monthly"), (4, 0, "Quarterly"), (5, 0, "Yearly")])
def test_calendar_periods(raw, kind, days, label):
    data = {**raw["bar_period"], "chart_data_type": 1, "historical_bar_period_type": kind,
            "historical_days_per_bar": days}
    result = describe_period(BarPeriod.model_validate(data))
    assert result.label == label
    assert result.seconds_per_bar is None


@pytest.mark.parametrize("kind", [1, 2, 3, 8, 9, 13, 18, 999])
def test_non_time_and_unknown_are_not_minutes(raw, kind):
    data = {**raw["bar_period"], "intraday_bar_period_type": kind, "parameters": [60, 2, 3, 4]}
    result = describe_period(BarPeriod.model_validate(data))
    assert result.seconds_per_bar is None
    assert "minute" not in result.label
    assert result.raw.parameters == [60, 2, 3, 4]


def test_switching_chart_period_propagates_without_config_change(setup_bridge, raw):
    config, path, _ = setup_bridge

    async def check():
        async with Client(create_server(config)) as client:
            for seconds in [60, 300]:
                raw["bar_period"]["parameters"][0] = seconds
                path.write_text(json.dumps(raw))
                for tool in ["get_snapshot", "get_study_values", "get_footprint", "get_data_health"]:
                    args = {"chart_id": "first"}
                    if tool == "get_study_values":
                        args["study_key"] = "ema"
                    result = await client.call_tool(tool, args)
                    assert result.structured_content["timeframe"]["seconds_per_bar"] == seconds
    asyncio.run(check())


def test_legacy_and_invalid_period_metadata(setup_bridge, raw):
    config, path, _ = setup_bridge
    reader = SnapshotReader(config)
    raw.pop("bar_period")
    path.write_text(json.dumps(raw))
    assert reader.read("first").status == "invalid"  # 1.2 must supply metadata
    raw["exporter_revision"] = "1.1"
    path.write_text(json.dumps(raw))
    result = reader.read("first")
    assert result.data is not None and result.timeframe is None
    assert "chart_timeframe_unavailable_rebuild_exporter" in result.warnings
