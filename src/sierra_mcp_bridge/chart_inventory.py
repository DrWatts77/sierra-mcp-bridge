"""One bounded, uncached inventory per tool call; no tool-supplied filesystem paths."""
import ctypes
import json
import os
import stat
from collections import Counter, defaultdict
from itertools import islice
from pathlib import Path

from .config import ChartConfig
from .contracts import Envelope, RawSnapshot
from .reader import SnapshotReader, unique_object


def opened_path(stream):
    """Verify the *opened handle* before reading bytes, including Windows junction races."""
    if os.name == "nt":
        import msvcrt
        from ctypes import wintypes
        function = ctypes.WinDLL("kernel32", use_last_error=True).GetFinalPathNameByHandleW
        function.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        function.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        length = function(msvcrt.get_osfhandle(stream.fileno()), buffer, len(buffer), 0)
        if not 0 < length < len(buffer):
            raise OSError("Unable to verify opened file")
        name = buffer.value
        if name.startswith("\\\\?\\UNC\\"):
            name = "\\\\" + name[8:]
        elif name.startswith("\\\\?\\"):
            name = name[4:]
        return Path(name)
    # Fail closed on systems without a handle path facility; Windows is the target.
    return Path(os.readlink(f"/proc/self/fd/{stream.fileno()}"))


def bounded_content(path, root, limit):
    if (not stat.S_ISREG(path.lstat().st_mode) or path.is_symlink()
            or path.is_junction() or path.resolve().parent != root):
        raise OSError("Discovery boundary rejected")
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or opened_path(stream).parent != root):
            raise OSError("Discovery boundary rejected")
        return stream.read(limit + 1)


class ChartInventory:
    def __init__(self, config, clock=None):
        self.config = config
        self.reader = SnapshotReader(config, **({"clock": clock} if clock else {}))
        self.charts = dict(self.reader.charts)
        self.results = {key: self.reader.read(key) for key in self.charts}
        self.warnings = Counter()
        self.discovered = set()
        if config.discovery and config.discovery.enabled:
            self._scan()

    def read(self, chart_id):
        return self.results.get(chart_id, Envelope(status="unavailable", chart_id=chart_id,
                                                   warnings=["chart_not_configured", *sorted(self.warnings)]))

    def _scan(self):
        options = self.config.discovery
        root = Path(options.directory).absolute()
        try:
            # Reject reparse components instead of silently changing the authorized root.
            if any(p.is_symlink() or p.is_junction() for p in (root, *root.parents)):
                raise OSError("Discovery root rejected")
            root = root.resolve(strict=True)
            with os.scandir(root) as entries:
                paths = [Path(e.path) for e in islice(entries, options.max_directory_entries + 1)]
            if len(paths) > options.max_directory_entries:
                self.warnings["discovery_directory_entry_limit"] += 1
                return
        except (OSError, RuntimeError):
            self.warnings["discovery_directory_unavailable"] += 1
            return
        candidates = sorted(p for p in paths if p.name.startswith("mcp_") and p.suffix == ".json")
        if len(candidates) > options.max_files:
            self.warnings["discovery_file_limit"] += 1
            return
        explicit_paths = {Path(c.snapshot_path).resolve(): key for key, c in self.charts.items()}
        groups = defaultdict(list)
        for key, result in self.results.items():
            identity = self.charts[key].export_id or (result.data.export_id if result.data else None)
            if identity:
                groups[identity].append((key, None))
        pending = []
        consumed = 0
        for path in candidates:
            # Explicit mappings always own their canonical path, even when invalid.
            remaining = options.max_total_bytes - consumed
            try:
                if path.resolve() in explicit_paths:
                    continue
                content = bounded_content(path, root, min(self.config.max_snapshot_bytes, remaining))
                consumed += len(content)
                if consumed > options.max_total_bytes:
                    self.warnings["discovery_total_byte_limit"] += 1
                    return  # Discard the entire discovered batch; never an arbitrary subset.
                if len(content) > self.config.max_snapshot_bytes:
                    self.warnings["discovery_snapshot_too_large"] += 1
                    continue
                raw = json.loads(content, object_pairs_hook=unique_object)
                if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int:
                    raise ValueError("Invalid schema")
                snapshot = RawSnapshot.model_validate(raw)
                if snapshot.exporter_revision != "1.6" or snapshot.export_id is None:
                    self.warnings["discovery_identity_revision_required"] += 1
                    continue
            except (OSError, RuntimeError):
                self.warnings["discovery_boundary_or_read_failed"] += 1
                continue
            except (ValueError, UnicodeError, RecursionError):
                self.warnings["discovery_invalid_snapshot"] += 1
                continue
            key = "export_" + snapshot.export_id
            chart = ChartConfig(id=key, chart_number=snapshot.chart_number, snapshot_path=str(path),
                                export_id=snapshot.export_id,
                                export_stale_after_seconds=options.export_stale_after_seconds)
            pending.append((key, chart, snapshot))
            groups[snapshot.export_id].append((key, chart))
        conflicts = {identity for identity, entries in groups.items() if len(entries) > 1}
        for identity in sorted(conflicts):
            self.warnings["duplicate_export_identity"] += 1
            for key, chart in groups[identity]:
                if chart is None:
                    self.results[key] = Envelope(status="invalid", chart_id=key,
                                                 warnings=["duplicate_export_identity"])
        for key, chart, snapshot in pending:
            if key in self.discovered:
                continue
            if key in self.charts:
                self.results[key] = Envelope(status="invalid", chart_id=key, warnings=["chart_id_conflict"])
                self.warnings["chart_id_conflict"] += 1
                continue
            self.charts[key] = chart
            self.discovered.add(key)
            if snapshot.export_id in conflicts:
                self.results[key] = Envelope(status="invalid", chart_id=key, warnings=["duplicate_export_identity"])
            else:
                self.reader.charts[key] = chart
                self.results[key] = self.reader.read(key, snapshot=snapshot)
                self.results[key].warnings.append("writer_liveness_unknown")
