"""Read complete bounded snapshots without caching failures as fresh data."""
import json
import time
from pathlib import Path

from pydantic import ValidationError

from .config import BridgeConfig
from .contracts import Envelope, Quality, RawSnapshot
from .timeframe import describe_period


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


class SnapshotReader:
    def __init__(self, config: BridgeConfig, clock=time.time):
        self.config = config
        self.charts = {c.id: c for c in config.charts}
        self.clock = clock

    def read(self, chart_id: str, *, snapshot: RawSnapshot | None = None) -> Envelope[RawSnapshot]:
        chart = self.charts.get(chart_id)
        if chart is None:
            return Envelope(status="unavailable", chart_id=chart_id, warnings=["chart_not_configured"])
        quality = Quality(source_mode=chart.source_mode, expected_delay_seconds=chart.expected_delay_seconds)

        def failure(status, warning):
            return Envelope(status=status, chart_id=chart_id, quality=quality, warnings=[warning])

        try:
            if snapshot is None:
                with Path(chart.snapshot_path).open("rb") as stream:
                    content = stream.read(self.config.max_snapshot_bytes + 1)
                if len(content) > self.config.max_snapshot_bytes:
                    return failure("invalid", "snapshot_too_large")
                raw = json.loads(content, object_pairs_hook=unique_object)
                if not isinstance(raw, dict):
                    return failure("invalid", "invalid_snapshot")
                if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
                    return failure("invalid", "unsupported_schema")
                snapshot = RawSnapshot.model_validate(raw)
        except FileNotFoundError:
            return failure("unavailable", "snapshot_missing")
        except OSError:
            return failure("unavailable", "snapshot_read_failed")
        except (ValueError, UnicodeError, ValidationError, RecursionError):
            return failure("invalid", "invalid_snapshot")
        if snapshot.chart_number != chart.chart_number:
            return failure("invalid", "chart_identity_mismatch")
        if chart.export_id is not None and snapshot.export_id != chart.export_id:
            return failure("invalid", "export_identity_mismatch")
        age = self.clock() - snapshot.snapshot_time_unix_ms / 1000
        quality.export_age_seconds = round(age, 3)
        if age < -5:
            return failure("invalid", "export_clock_in_future")
        warnings = ["market_event_time_unavailable", "bar_time_timezone_unavailable",
                    "bid_ask_unverified_values_suppressed", "vap_and_volume_units_unverified"]
        if snapshot.chart_timezone:
            warnings.remove("bar_time_timezone_unavailable")
        timeframe = describe_period(snapshot.bar_period) if snapshot.bar_period else None
        if timeframe is None:
            warnings.append("chart_timeframe_unavailable_rebuild_exporter")
        if chart.source_mode != "live":
            warnings.append("source_mode_" + chart.source_mode)
        status = "degraded"
        if age > chart.export_stale_after_seconds:
            status = "stale"
            warnings.append("export_stale")
        return Envelope(status=status, chart_id=chart_id, as_of=snapshot.snapshot_time_unix_ms,
                        quality=quality, timeframe=timeframe, data=snapshot, warnings=warnings)
