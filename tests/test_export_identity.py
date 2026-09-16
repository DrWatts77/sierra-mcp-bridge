import json

import pytest

from sierra_mcp_bridge.reader import SnapshotReader
from test_history import add_history


def test_export_identity_pin_and_legacy_compatibility(setup_bridge, raw):
    config, path, _ = setup_bridge
    reader = SnapshotReader(config)
    assert reader.read("first").data  # Unpinned legacy configuration still works.
    config.charts[0].export_id = "a" * 32
    assert reader.read("first").warnings == ["export_identity_mismatch"]
    snapshot = add_history(raw)
    snapshot.update(exporter_revision="1.6", export_id="a" * 32)
    path.write_text(json.dumps(snapshot))
    assert reader.read("first").data.export_id == "a" * 32
    # Same chart number from another chartbook must not satisfy a pinned mapping.
    snapshot["export_id"] = "b" * 32
    path.write_text(json.dumps(snapshot))
    assert reader.read("first").warnings == ["export_identity_mismatch"]


@pytest.mark.parametrize("identity", [None, "", "../export", "A" * 32, "g" * 32, "a" * 33])
def test_revision_16_requires_valid_identity(setup_bridge, raw, identity):
    config, path, _ = setup_bridge
    snapshot = add_history(raw)
    snapshot.update(exporter_revision="1.6", export_id=identity)
    path.write_text(json.dumps(snapshot))
    assert SnapshotReader(config).read("first").warnings == ["invalid_snapshot"]


@pytest.mark.parametrize("field", ["history", "chart_timezone", "bar_period"])
def test_revision_16_keeps_existing_required_metadata(setup_bridge, raw, field):
    config, path, _ = setup_bridge
    snapshot = add_history(raw)
    snapshot.update(exporter_revision="1.6", export_id="a" * 32)
    snapshot.pop(field)
    path.write_text(json.dumps(snapshot))
    assert SnapshotReader(config).read("first").warnings == ["invalid_snapshot"]
