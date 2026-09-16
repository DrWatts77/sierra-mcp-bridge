"""Regenerate public configuration and input schemas from the authoritative models."""
import json
from pathlib import Path

from sierra_mcp_bridge.config import BridgeConfig
from sierra_mcp_bridge.contracts import RawSnapshot

destination = Path(__file__).resolve().parents[1] / "schemas"
destination.mkdir(exist_ok=True)
for name, model in [("bridge-config", BridgeConfig), ("snapshot-v1", RawSnapshot)]:
    (destination / f"{name}.schema.json").write_text(
        json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8"
    )
