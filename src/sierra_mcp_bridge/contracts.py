"""Bounded wire models; schema 1 export time never implies market freshness."""
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .timeframe import BarPeriod, Timeframe


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class RawLevel(Model):
    price: float
    volume: float = Field(ge=0)
    bid_volume: float = Field(ge=0)
    ask_volume: float = Field(ge=0)
    delta: float


class StudyInput(Model):
    index: int = Field(ge=0, le=127)
    name: str = Field(max_length=4096)
    type_code: int
    value: bool | int | float | None
    reason: str | None

    @model_validator(mode="after")
    def availability(self):
        if (self.value is None) != (self.reason is not None):
            raise ValueError("Input availability and reason disagree")
        return self


class StudyMetadata(Model):
    short_name: str | None = Field(max_length=4096)
    primary_color: str | None = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    secondary_color: str | None = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    secondary_color_used: bool | None
    latest_data_color_raw: str | None = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    draw_style_code: int | None
    line_style_code: int | None
    line_width: int | None
    hide_study_setting_raw: int
    graph_region_raw: int
    inputs: list[StudyInput] = Field(max_length=128)


class RawStudy(Model):
    metadata: StudyMetadata | None = None
    study_name: str | None = Field(default=None, max_length=4096)
    subgraph_name: str | None = Field(default=None, max_length=4096)
    study_id: int = Field(ge=1)
    subgraph_index: int = Field(ge=0, le=59)
    value: float | None
    reason: Literal["study_unavailable", "nonfinite_value"] | None

    @model_validator(mode="after")
    def availability(self):
        if (self.value is None) != (self.reason is not None):
            raise ValueError("Study availability and reason disagree")
        return self


class BarData(Model):
    bar_index: int = Field(ge=0)
    bar_start_sc_datetime: float
    bar_start_chart_time: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}$")
    is_closed: bool
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None = Field(ge=0)


class HistoryBar(BarData):
    studies: list[RawStudy] = Field(max_length=8)


class RawSnapshot(Model):
    schema_version: Literal[1]
    snapshot_time_unix_ms: int = Field(ge=0)
    chart_number: int = Field(ge=1)
    bar_index: int = Field(ge=0)
    bar_start_sc_datetime: float
    symbol: str = Field(min_length=1, max_length=256)
    last_price: float
    vwap_scope: Literal["current_bar"]
    vwap: float | None
    volume: float = Field(ge=0)
    footprint_volume: float = Field(ge=0)
    footprint: list[RawLevel] = Field(max_length=20000)
    # Additive extension to v1; older exporters omit these fields.
    exporter_revision: Literal["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"] | None = None
    export_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    chart_timezone: str | None = Field(default=None, max_length=256)
    history: list[HistoryBar] | None = Field(default=None, max_length=200)
    bar_period: BarPeriod | None = None
    studies: list[RawStudy] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def unique_studies(self):
        if self.exporter_revision == "1.6" and self.export_id is None:
            raise ValueError("Exporter 1.6 requires export identity")
        if self.exporter_revision in ("1.2", "1.3", "1.4", "1.5", "1.6") and self.bar_period is None:
            raise ValueError("Exporter requires bar period metadata")
        if len({(s.study_id, s.subgraph_index) for s in self.studies}) != len(self.studies):
            raise ValueError("Duplicate study outputs")
        if self.exporter_revision in ("1.3", "1.4", "1.5", "1.6") and (self.history is None or self.chart_timezone is None):
            raise ValueError("Exporter 1.3 requires history and timezone")
        if self.history is not None:
            expected = list(range(max(0, self.bar_index - 199), self.bar_index + 1))
            if [bar.bar_index for bar in self.history] != expected:
                raise ValueError("History must cover the last up to 200 contiguous loaded bars")
            pairs = {(s.study_id, s.subgraph_index) for s in self.studies}
            for bar in self.history:
                keys = [(s.study_id, s.subgraph_index) for s in bar.studies]
                if len(keys) != len(set(keys)) or set(keys) != pairs:
                    raise ValueError("History study mappings disagree")
                if bar.is_closed != (bar.bar_index < self.bar_index):
                    raise ValueError("History closure state disagrees with Sierra latest-bar semantics")
            last = self.history[-1]
            def values(studies):
                return [s.model_dump(exclude={"study_name", "subgraph_name", "metadata"}) for s in studies]
            if last.bar_start_sc_datetime != self.bar_start_sc_datetime or values(last.studies) != values(self.studies):
                raise ValueError("Latest history sample disagrees with snapshot")
        return self


class Quality(Model):
    source_mode: Literal["unknown", "delayed", "live", "replay", "synthetic"]
    source_mode_basis: Literal["operator_configuration"] = "operator_configuration"
    expected_delay_seconds: int | None
    export_age_seconds: float | None = None
    market_event_time_unix_ms: int | None = None
    market_event_age_seconds: float | None = None
    market_freshness: Literal["unknown"] = "unknown"
    bid_ask_availability: Literal["unverified"] = "unverified"
    vap_provenance: Literal["unverified"] = "unverified"
    volume_units: Literal["unverified"] = "unverified"


T = TypeVar("T")


class Envelope(Model, Generic[T]):
    status: Literal["ok", "degraded", "stale", "unavailable", "invalid"]
    schema_version: Literal[1] = 1
    chart_id: str
    as_of: int | None = None  # export time, UTC milliseconds
    quality: Quality | None = None
    timeframe: Timeframe | None = None
    data: T | None = None
    warnings: list[str] = Field(default_factory=list)


class SnapshotData(Model):
    chart_number: int
    symbol: str
    bar_index: int
    bar_start_sc_datetime: float
    last_price: float
    volume: float
    vwap: float | None
    vwap_scope: Literal["current_bar"]
    footprint_volume: float


class StudyValue(Model):
    metadata: StudyMetadata | None = None
    study_name: str | None = None
    subgraph_name: str | None = None
    key: str
    label: str
    study_id: int
    subgraph_index: int
    value: float | None
    reason: str | None
    bar_index: int
    bar_start_sc_datetime: float


class FootprintLevel(Model):
    price: float
    volume: float
    bid_volume: float | None = None
    ask_volume: float | None = None
    delta: float | None = None


class FootprintData(Model):
    levels: list[FootprintLevel]
    total_levels: int
    next_offset: int | None
    bar_index: int


class StudyHistoryPoint(BarData):
    value: float | None
    reason: str | None


class StudyHistoryData(Model):
    metadata: StudyMetadata | None = None
    study_name: str | None = None
    subgraph_name: str | None = None
    key: str
    label: str
    study_id: int
    subgraph_index: int
    chart_timezone: str | None
    timestamp_basis: Literal["chart_local_time"] = "chart_local_time"
    order: Literal["oldest_first"] = "oldest_first"
    history_basis: Literal["current_study_calculation"] = "current_study_calculation"
    available_bars: int
    returned_bars: int
    includes_forming_bar: bool
    bars: list[StudyHistoryPoint]
