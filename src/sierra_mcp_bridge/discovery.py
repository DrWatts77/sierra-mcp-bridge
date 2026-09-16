"""Discover only outputs deliberately selected in the Sierra bridge."""
from .config import StudyConfig
from .contracts import StudyMetadata


class StudyDescriptor(StudyConfig):
    metadata: StudyMetadata | None = None
    study_name: str | None = None
    subgraph_name: str | None = None


def describe(study, alias=None):
    name = study.study_name or None
    subgraph = study.subgraph_name or None
    return StudyDescriptor(
        key=alias.key if alias else f"id{study.study_id}_sg{study.subgraph_index + 1}",
        label=(name or (alias.label if alias else f"Study ID {study.study_id}"))[:128],
        study_id=study.study_id, subgraph_index=study.subgraph_index,
        study_name=name, subgraph_name=subgraph, metadata=study.metadata)


def discover(chart, snapshot):
    if snapshot is None:
        return []
    allowed = {(s.study_id, s.subgraph_index) for s in chart.studies}
    return [describe(s) for s in snapshot.studies
            if chart.discover_exported_studies or (s.study_id, s.subgraph_index) in allowed]


def resolve(chart, snapshot, key):
    if chart is None:
        return None
    alias = next((s for s in chart.studies if s.key == key), None)
    if alias:
        output = next((s for s in snapshot.studies if (s.study_id, s.subgraph_index) ==
                       (alias.study_id, alias.subgraph_index)), None) if snapshot else None
        return describe(output, alias) if output else StudyDescriptor(**alias.model_dump())
    return next((s for s in discover(chart, snapshot) if s.key == key), None)
