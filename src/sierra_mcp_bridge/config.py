"""Operator-owned chart allowlist. Tool arguments never become file paths."""
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class StudyConfig(ConfigModel):
    key: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    label: str = Field(min_length=1, max_length=128)
    study_id: int = Field(ge=1)
    subgraph_index: int = Field(ge=0, le=59)


class ChartConfig(ConfigModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    chart_number: int = Field(ge=1)
    snapshot_path: str = Field(min_length=1)
    export_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    source_mode: Literal["unknown", "delayed", "live", "replay", "synthetic"] = "unknown"
    expected_delay_seconds: int | None = Field(default=None, ge=0)
    export_stale_after_seconds: int = Field(default=120, ge=1, le=86400)
    studies: list[StudyConfig] = Field(default_factory=list, max_length=25)
    discover_exported_studies: bool = True

    @model_validator(mode="after")
    def unique_studies(self):
        for study in self.studies:
            if re.fullmatch(r"id\d+_sg\d+", study.key) and study.key != f"id{study.study_id}_sg{study.subgraph_index + 1}":
                raise ValueError("Canonical study keys cannot alias another output")
        if len({s.key for s in self.studies}) != len(self.studies):
            raise ValueError("Study keys must be unique per chart")
        if len({(s.study_id, s.subgraph_index) for s in self.studies}) != len(self.studies):
            raise ValueError("Study mappings must be unique per chart")
        return self


class DiscoveryConfig(ConfigModel):
    enabled: bool = False
    directory: str = Field(min_length=1)
    max_files: int = Field(default=64, ge=1, le=64)
    max_directory_entries: int = Field(default=512, ge=1, le=4096)
    max_total_bytes: int = Field(default=16_000_000, ge=1024, le=200_000_000)
    export_stale_after_seconds: int = Field(default=120, ge=1, le=86400)


class BridgeConfig(ConfigModel):
    charts: list[ChartConfig] = Field(default_factory=list, max_length=64)
    discovery: DiscoveryConfig | None = None
    max_snapshot_bytes: int = Field(default=2_000_000, ge=1024, le=100_000_000)

    @model_validator(mode="after")
    def unique_charts(self):
        if not self.charts and not (self.discovery and self.discovery.enabled):
            raise ValueError("Configure at least one chart or enable discovery")
        if len({c.id for c in self.charts}) != len(self.charts):
            raise ValueError("Chart IDs must be unique")
        paths = [Path(c.snapshot_path).resolve() for c in self.charts]
        if len(set(paths)) != len(paths):
            raise ValueError("Each chart must have a unique snapshot path")
        return self


def load_config(path: Path) -> BridgeConfig:
    path = path.resolve()
    config = BridgeConfig.model_validate(json.loads(path.read_text(encoding="utf-8-sig")))
    for chart in config.charts:
        chart.snapshot_path = str((path.parent / chart.snapshot_path).resolve())
    if config.discovery:
        config.discovery.directory = str((path.parent / config.discovery.directory).absolute())
    # Check aliases again after resolving paths relative to the config file.
    return BridgeConfig.model_validate(config.model_dump())
