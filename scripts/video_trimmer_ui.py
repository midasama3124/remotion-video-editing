#!/usr/bin/env python3
"""Serve the browser UI used to trim A/B roll segments."""

import http.server
import json
import mimetypes
import os
import re
import struct
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

WORKSPACE = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
PORT = 8765
SESSION_BACKUP = WORKSPACE / ".trimmer_ui_session_backup.json"
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v", ".mkv"}
FPS = 30

ZOOM_MIN = 0.5
ZOOM_MAX = 2.0
POSITION_MIN = -600.0
POSITION_MAX = 600.0

BUBBLE_ZOOM_MIN = 0.2
BUBBLE_ZOOM_MAX = 3.0
BUBBLE_SOFTNESS_MIN = 0.0
BUBBLE_SOFTNESS_MAX = 1.0

DEFAULT_LAYER_TRANSFORM = {
    "zoom": 1.0,
    "posX": 0.0,
    "posY": 0.0,
}

DEFAULT_BUBBLE_TRANSFORM = {
    "posX": -270.0,
    "posY": 700.0,
    "zoom": 1.0,
    "softness": 0.3,
}

DEFAULT_VISUAL_TRANSFORMS = {
    "aroll": dict(DEFAULT_LAYER_TRANSFORM),
    "broll": dict(DEFAULT_LAYER_TRANSFORM),
    "bubble": dict(DEFAULT_BUBBLE_TRANSFORM),
}

FORMAT_MAP = {
    "Half-And-Half Split": "half_and_half",
    "B-Roll Only": "broll_only",
    "B-Roll Main, A-Roll Bubble": "broll_bubble",
}
FALLBACK_LAYOUT = "aroll_only"

# Ensure .webm is registered
mimetypes.add_type("video/webm", ".webm")


# ─── Helpers ────────────────────────────────────────────────────────────────
def segments_path(project_dir: Path, video_filename: str) -> Path:
    stem = Path(video_filename).stem
    return project_dir / "video" / f"{stem}_segments.json"


def waveform_path(project_dir: Path, video_filename: str) -> Path:
    stem = Path(video_filename).stem
    return project_dir / "video" / f"{stem}_waveform.json"


# ─── Partition and Normalization Helpers ─────────────────────────────────────
def partition_index_from_time(segment: dict, time: float) -> int:
    """
    Find which partition a given time overlaps with.
    Returns partition index (0-based), or 0 if no partitions exist.
    Returns -1 if time is outside segment bounds.
    """
    partitions = segment.get("partitions", [])
    if not partitions:
        return 0
    for idx, part in enumerate(partitions):
        if part.get("start") is not None and part.get("end") is not None:
            if part["start"] <= time < part["end"]:
                return idx
    return -1


def normalize_aroll_json(data: dict) -> dict:
    """
    Ensure A-Roll JSON has partitions field on all segments.
    Backfill missing fields for backward compatibility.
    """
    if not isinstance(data, dict):
        return {"project": "unknown", "type": "aroll", "video": "", "segments": []}
    
    segments = data.get("segments", [])
    if not isinstance(segments, list):
        segments = []
    
    normalized = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        normalized_seg = {
            "name": seg.get("name", "Unnamed"),
            "start": seg.get("start"),
            "end": seg.get("end"),
            "visual_transforms": normalize_visual_transforms(seg.get("visual_transforms")),
        }
        # Ensure partitions field; if missing or invalid, initialize to empty
        if "partitions" in seg and isinstance(seg["partitions"], list):
            normalized_seg["partitions"] = seg["partitions"]
        else:
            normalized_seg["partitions"] = []
        normalized.append(normalized_seg)
    
    return {
        "project": data.get("project", "unknown"),
        "type": "aroll",
        "video": data.get("video", ""),
        "segments": normalized,
    }


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_layer_transform(layer: dict | None) -> dict:
    layer = layer if isinstance(layer, dict) else {}
    return {
        "zoom": round(_clamp(_safe_float(layer.get("zoom"), 1.0), ZOOM_MIN, ZOOM_MAX), 4),
        "posX": round(_clamp(_safe_float(layer.get("posX"), 0.0), POSITION_MIN, POSITION_MAX), 3),
        "posY": round(_clamp(_safe_float(layer.get("posY"), 0.0), POSITION_MIN, POSITION_MAX), 3),
    }


def _normalize_bubble_transform(bubble: dict | None) -> dict:
    b = bubble if isinstance(bubble, dict) else {}
    return {
        "posX": round(_clamp(_safe_float(b.get("posX"), DEFAULT_BUBBLE_TRANSFORM["posX"]), -540.0, 540.0), 3),
        "posY": round(_clamp(_safe_float(b.get("posY"), DEFAULT_BUBBLE_TRANSFORM["posY"]), -960.0, 960.0), 3),
        "zoom": round(_clamp(_safe_float(b.get("zoom"), DEFAULT_BUBBLE_TRANSFORM["zoom"]), BUBBLE_ZOOM_MIN, BUBBLE_ZOOM_MAX), 4),
        "softness": round(_clamp(_safe_float(b.get("softness"), DEFAULT_BUBBLE_TRANSFORM["softness"]), BUBBLE_SOFTNESS_MIN, BUBBLE_SOFTNESS_MAX), 2),
    }


def normalize_visual_transforms(transforms: dict | None) -> dict:
    """
    Normalize and clamp visual transforms for one B-Roll segment.
    """
    transforms = transforms if isinstance(transforms, dict) else {}
    return {
        "aroll": _normalize_layer_transform(transforms.get("aroll")),
        "broll": _normalize_layer_transform(transforms.get("broll")),
        "bubble": _normalize_bubble_transform(transforms.get("bubble")),
    }


def normalize_split_ratio(value, default: float = 0.5) -> float:
    return round(_clamp(_safe_float(value, default), 0.0, 1.0), 4)


def normalize_broll_json(data: dict) -> dict:
    """
    Ensure B-Roll JSON has aroll_partition_index field on all segments.
    Backfill missing fields for backward compatibility.
    """
    if not isinstance(data, dict):
        return {"project": "unknown", "type": "broll", "video": "", "segments": []}
    
    segments = data.get("segments", [])
    if not isinstance(segments, list):
        segments = []
    
    normalized = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        aroll_idx = seg.get("aroll_segment_index")
        # A-Roll Only is the implicit format for segments without an A-Roll assignment.
        # Any other format requires an A-Roll, so fall back to A-Roll Only when none is set.
        if aroll_idx is None:
            broll_format = "A-Roll Only"
        else:
            broll_format = seg.get("broll_format", "Half-And-Half Split")
        normalized_seg = {
            "name": seg.get("name", "Unnamed"),
            "start": seg.get("start"),
            "end": seg.get("end"),
            "aroll_segment_index": aroll_idx,
            "aroll_segment_name": seg.get("aroll_segment_name"),
            "max_duration": seg.get("max_duration"),
            "broll_format": broll_format,
            "splitRatio": normalize_split_ratio(seg.get("splitRatio"), 0.5),
            "visual_transforms": normalize_visual_transforms(seg.get("visual_transforms")),
        }
        # Ensure aroll_partition_index field; defaults to 0 if missing
        if "aroll_partition_index" in seg:
            normalized_seg["aroll_partition_index"] = seg["aroll_partition_index"]
        else:
            normalized_seg["aroll_partition_index"] = 0
        normalized.append(normalized_seg)
    
    return {
        "project": data.get("project", "unknown"),
        "type": "broll",
        "video": data.get("video", ""),
        "segments": normalized,
    }


def auto_assign_broll_to_partitions(aroll_seg: dict, broll_segments: list) -> None:
    """
    For a given A-Roll segment that just had partitions created/modified,
    auto-assign any B-Roll segments that reference it to the correct partition
    based on time overlap.
    Updates broll_segments in place.
    
    Args:
        aroll_seg: The A-Roll segment with partitions
        broll_segments: List of all B-Roll segments (will be modified)
    """
    aroll_idx = None
    for i, seg in enumerate(aroll_seg.get("_segments_list", [])):
        if seg is aroll_seg:
            aroll_idx = i
            break
    
    if aroll_idx is None:
        return
    
    partitions = aroll_seg.get("partitions", [])
    if not partitions:
        # No partitions, all B-Roll should use partition_index 0
        for bseg in broll_segments:
            if bseg.get("aroll_segment_index") == aroll_idx:
                bseg["aroll_partition_index"] = 0
        return
    
    # For each B-Roll segment, find which partition its time overlaps with
    for bseg in broll_segments:
        if bseg.get("aroll_segment_index") != aroll_idx:
            continue
        
        bseg_start = bseg.get("start")
        if bseg_start is None:
            bseg["aroll_partition_index"] = 0
            continue
        
        best_partition = 0
        for pidx, part in enumerate(partitions):
            part_start = part.get("start")
            part_end = part.get("end")
            if part_start is not None and part_end is not None:
                if part_start <= bseg_start < part_end:
                    best_partition = pidx
                    break
        
        bseg["aroll_partition_index"] = best_partition
        
        # Update max_duration to partition duration
        partition = partitions[best_partition]
        part_start = partition.get("start")
        part_end = partition.get("end")
        if part_start is not None and part_end is not None:
            bseg["max_duration"] = round(part_end - part_start, 3)


def _strip_part_suffix(name: str) -> str:
    return re.sub(r"\s+-\s+Part\s+[A-Z]+$", "", str(name or "")).strip() or "Segment"


def split_broll_segments_for_aroll_partitions(
    aroll_seg: dict,
    aroll_idx: int,
    broll_segments: list[dict],
) -> list[dict]:
    """
    Rebuild B-Roll entries linked to one A-Roll segment so there is exactly one
    B-Roll entry per A-Roll partition.

    Behavior:
    - If no linked B-Roll entries exist, returns original list unchanged.
    - If linked entries exist, they are consolidated into one source range
      (min start, max end), then split at A-Roll partition boundaries.
    - If A-Roll has no partitions, keeps one linked B-Roll entry with
      partition_index = 0.
    """
    linked_positions: list[int] = []
    linked_segments: list[dict] = []

    for pos, bseg in enumerate(broll_segments):
        if bseg.get("aroll_segment_index") == aroll_idx:
            linked_positions.append(pos)
            linked_segments.append(bseg)

    if not linked_segments:
        return broll_segments

    # Build a single source segment from existing linked entries so repeated
    # repartitioning does not multiply entries.
    starts = [float(s.get("start")) for s in linked_segments if s.get("start") is not None]
    ends = [float(s.get("end")) for s in linked_segments if s.get("end") is not None]
    if not starts or not ends:
        return broll_segments

    source = dict(min(linked_segments, key=lambda s: float(s.get("start", 10**9))))
    source_start = round(min(starts), 3)
    source_end = round(max(ends), 3)
    if source_end <= source_start:
        return broll_segments

    base_name = _strip_part_suffix(source.get("name", "Segment"))
    aroll_name = aroll_seg.get("name") or f"Segment {aroll_idx + 1}"
    aroll_start = aroll_seg.get("start")
    aroll_end = aroll_seg.get("end")
    partitions = aroll_seg.get("partitions", []) if isinstance(aroll_seg.get("partitions"), list) else []

    replacement: list[dict] = []

    if not partitions:
        merged = dict(source)
        merged["name"] = base_name
        merged["start"] = source_start
        merged["end"] = source_end
        merged["aroll_segment_index"] = aroll_idx
        merged["aroll_partition_index"] = 0
        merged["aroll_segment_name"] = aroll_name
        if aroll_start is not None and aroll_end is not None:
            merged["max_duration"] = round(float(aroll_end) - float(aroll_start), 3)
        replacement.append(merged)
    else:
        if aroll_start is None:
            aroll_start = partitions[0].get("start")
        if aroll_end is None:
            aroll_end = partitions[-1].get("end")

        if aroll_start is None or aroll_end is None or float(aroll_end) <= float(aroll_start):
            return broll_segments

        for pidx, part in enumerate(partitions):
            p_start = part.get("start")
            p_end = part.get("end")
            if p_start is None or p_end is None:
                continue

            # Map A-Roll partition offsets onto the selected B-Roll source span.
            offset_start = float(p_start) - float(aroll_start)
            offset_end = float(p_end) - float(aroll_start)
            b_start = round(source_start + offset_start, 3)
            b_end = round(source_start + offset_end, 3)

            # Clamp to original source span to avoid overshooting.
            b_start = max(source_start, min(source_end, b_start))
            b_end = max(source_start, min(source_end, b_end))
            if b_end <= b_start:
                continue

            seg = dict(source)
            seg["name"] = f"{base_name} - Part {chr(65 + pidx)}"
            seg["start"] = round(b_start, 3)
            seg["end"] = round(b_end, 3)
            seg["aroll_segment_index"] = aroll_idx
            seg["aroll_partition_index"] = pidx
            seg["aroll_segment_name"] = aroll_name
            seg["max_duration"] = round(float(p_end) - float(p_start), 3)
            replacement.append(seg)

    if not replacement:
        return broll_segments

    first_pos = linked_positions[0]
    result: list[dict] = []
    inserted = False
    for pos, bseg in enumerate(broll_segments):
        if pos in linked_positions:
            if not inserted and pos == first_pos:
                result.extend(replacement)
                inserted = True
            continue
        result.append(bseg)

    return result


def list_projects() -> list[str]:
    projects: list[str] = []
    for child in WORKSPACE.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if child.name in {"assets", "docs", "scripts"}:
            continue
        if (child / "video").is_dir():
            projects.append(child.name)
    return sorted(projects)


def list_project_videos(project_name: str) -> list[str]:
    p = WORKSPACE / project_name / "video"
    if not p.is_dir():
        return []
    files = [f.name for f in p.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXTS]
    return sorted(files)


def build_mode_videos(project_name: str, mode: str) -> list[str]:
    all_videos = list_project_videos(project_name)
    if mode == "aroll":
        return [v for v in all_videos if v.lower().startswith("aroll")]
    return [v for v in all_videos if not v.lower().startswith("aroll")]


def normalize_session(project: str, mode: str, video_filename: str) -> dict:
    mode = "aroll" if mode == "aroll" else "broll"
    project = str(project).strip()
    video_filename = os.path.basename(str(video_filename).strip())
    return {
        "project": project,
        "mode": mode,
        "videoFilename": video_filename,
        "fps": 30,
    }


def _normalize_preset_item(preset: dict) -> dict | None:
    if not isinstance(preset, dict):
        return None

    name = str(preset.get("name", "")).strip()
    if not name:
        return None

    created_at = str(preset.get("createdAt", "")).strip()
    if not created_at:
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    return {
        "name": name,
        "aroll": _normalize_layer_transform(preset.get("aroll")),
        "broll": _normalize_layer_transform(preset.get("broll")),
        "createdAt": created_at,
    }


def normalize_backup_presets(raw_presets: dict | None) -> dict:
    if not isinstance(raw_presets, dict):
        return {}

    normalized: dict[str, list[dict]] = {}
    for format_name, presets in raw_presets.items():
        key = str(format_name).strip()
        if not key:
            continue
        if not isinstance(presets, list):
            normalized[key] = []
            continue

        clean_list: list[dict] = []
        for preset in presets:
            item = _normalize_preset_item(preset)
            if item is not None:
                clean_list.append(item)
        normalized[key] = clean_list

    return normalized


def normalize_backup_data(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    session = normalize_session(
        data.get("project", ""),
        data.get("mode", "aroll"),
        data.get("videoFilename", ""),
    )
    session["presets"] = normalize_backup_presets(data.get("presets"))
    return session


def load_backup_data() -> dict | None:
    if not SESSION_BACKUP.exists():
        return None
    try:
        raw = json.loads(SESSION_BACKUP.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None

    normalized = normalize_backup_data(raw)
    # Keep legacy files forward-compatible by injecting missing presets key.
    if raw.get("presets") != normalized.get("presets") or "presets" not in raw:
        try:
            SESSION_BACKUP.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), "utf-8")
        except OSError:
            pass
    return normalized


def choose_default_session() -> dict:
    projects = list_projects()
    if not projects:
        sys.exit(f"Error: no project with a video folder found in {WORKSPACE}")

    first_project = projects[0]
    aroll_videos = build_mode_videos(first_project, "aroll")
    if aroll_videos:
        return normalize_session(first_project, "aroll", aroll_videos[0])

    broll_videos = build_mode_videos(first_project, "broll")
    if broll_videos:
        return normalize_session(first_project, "broll", broll_videos[0])

    sys.exit(f"Error: no supported video files found in {WORKSPACE / first_project / 'video'}")


def load_backup_session() -> dict | None:
    data = load_backup_data()
    if data is None:
        return None
    return normalize_session(
        data.get("project", ""),
        data.get("mode", "aroll"),
        data.get("videoFilename", ""),
    )


def save_backup_session(session: dict) -> None:
    existing = load_backup_data() or {"presets": {}}
    normalized_session = normalize_session(
        session.get("project", ""),
        session.get("mode", "aroll"),
        session.get("videoFilename", ""),
    )
    existing.update(normalized_session)
    existing["presets"] = normalize_backup_presets(existing.get("presets"))
    SESSION_BACKUP.write_text(json.dumps(existing, ensure_ascii=False, indent=2), "utf-8")


def read_backup_presets() -> dict:
    data = load_backup_data()
    if data is None:
        return {}
    return normalize_backup_presets(data.get("presets"))


def write_backup_presets(presets: dict) -> None:
    data = load_backup_data() or normalize_session("", "aroll", "")
    data["presets"] = normalize_backup_presets(presets)
    SESSION_BACKUP.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_json_body(handler: http.server.BaseHTTPRequestHandler) -> dict | None:
    try:
        content_len = int(handler.headers.get("Content-Length", 0))
        body = handler.rfile.read(content_len) if content_len > 0 else b"{}"
        data = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _broll_segments_file(project_name: str, video_filename: str = "broll_main.mp4") -> Path:
    return segments_path(WORKSPACE / project_name, video_filename)


def load_broll_data_for_project(project_name: str, video_filename: str = "broll_main.mp4") -> tuple[dict, Path]:
    p = _broll_segments_file(project_name, video_filename)
    if p.exists():
        raw = json.loads(p.read_text("utf-8"))
    else:
        raw = {
            "project": project_name,
            "type": "broll",
            "video": video_filename,
            "segments": [],
        }
    return normalize_broll_json(raw), p


def _normalize_input_props_segment(index: int, raw: dict | None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    transforms = raw.get("visualTransforms")
    if transforms is None:
        transforms = raw.get("visual_transforms")
    return {
        "index": index,
        "splitRatio": normalize_split_ratio(raw.get("splitRatio"), 0.5),
        "visualTransforms": normalize_visual_transforms(transforms),
    }


def _load_existing_input_props(output_dir: Path) -> dict[int, dict]:
    input_props_path = output_dir / "inputProps.json"
    if not input_props_path.is_file():
        return {}
    try:
        raw = json.loads(input_props_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    segments = raw.get("segments", []) if isinstance(raw, dict) else []
    if not isinstance(segments, list):
        return {}

    by_index: dict[int, dict] = {}
    for idx, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        index = seg.get("index")
        if not isinstance(index, int):
            index = idx
        if index < 0:
            continue
        by_index[index] = _normalize_input_props_segment(index, seg)
    return by_index


def build_remotion_input_props_from_broll(
    broll_segments: list,
    existing_input_props: dict[int, dict] | None = None,
) -> dict:
    existing_input_props = existing_input_props or {}
    props_segments: list[dict] = []

    for idx, bseg in enumerate(broll_segments):
        if not isinstance(bseg, dict):
            bseg = {}

        from_existing = existing_input_props.get(idx)
        # Trimmer-managed B-Roll JSON is the source of truth. Existing inputProps
        # is only a fallback for missing/legacy values.
        split_ratio = normalize_split_ratio(
            bseg.get("splitRatio", (from_existing or {}).get("splitRatio", 0.5)),
            0.5,
        )

        transforms_src = bseg.get("visual_transforms")
        if transforms_src is None:
            transforms_src = (from_existing or {}).get("visualTransforms")
        transforms = normalize_visual_transforms(transforms_src)

        props_segments.append(
            {
                "index": idx,
                "splitRatio": split_ratio,
                "visualTransforms": transforms,
            }
        )

    return {"segments": props_segments}


def validate_session(session: dict) -> tuple[bool, str]:
    project = session["project"]
    mode = session["mode"]
    filename = session["videoFilename"]

    if project not in list_projects():
        return False, f"Unknown project: {project}"

    choices = build_mode_videos(project, mode)
    if filename not in choices:
        return False, f"Video not available for {project}/{mode}: {filename}"

    full = WORKSPACE / project / "video" / filename
    if not full.is_file():
        return False, f"Not found: {full}"
    return True, ""


class SessionStore:
    def __init__(self, session: dict, restored_from_backup: bool = False):
        self._lock = threading.Lock()
        self._session = session
        self._restored_from_backup = bool(restored_from_backup)

    def get(self) -> dict:
        with self._lock:
            return dict(self._session)

    def set(self, session: dict) -> None:
        with self._lock:
            self._session = dict(session)
            self._restored_from_backup = False

    def restored_from_backup(self) -> bool:
        with self._lock:
            return self._restored_from_backup


def has_audio_stream(video_path: Path) -> bool:
    """Return True when media has at least one audio stream."""
    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    try:
        probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=6)
    except subprocess.TimeoutExpired:
        return False
    if probe.returncode != 0:
        return False
    return "audio" in (probe.stdout or "")


def build_waveform(video_path: Path, bars: int = 2400) -> dict:
    """Generate normalized waveform peaks using ffmpeg-decoded mono audio."""
    # Fast fail for files with no audio stream (common in some WebM exports).
    if not has_audio_stream(video_path):
        raise RuntimeError("No audio stream in this video")

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "8000",
        "-f",
        "f32le",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=25)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Audio extraction timed out") from exc
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="ignore") or "ffmpeg failed")

    raw = proc.stdout
    if not raw:
        raise RuntimeError("No audio data extracted")

    sample_count = len(raw) // 4
    if sample_count <= 0:
        raise RuntimeError("Invalid PCM data")

    vals = struct.unpack(f"<{sample_count}f", raw[: sample_count * 4])
    block = max(1, sample_count // bars)
    peaks: list[float] = []

    for i in range(bars):
        start = i * block
        if start >= sample_count:
            break
        end = min(sample_count, start + block)
        max_amp = 0.0
        for s in vals[start:end]:
            a = abs(float(s))
            if a > max_amp:
                max_amp = a
        peaks.append(max_amp)

    max_peak = max(peaks) if peaks else 0.0
    if max_peak > 0:
        peaks = [round(p / max_peak, 4) for p in peaks]

    stat = video_path.stat()
    return {
        "peaks": peaks,
        "source": {
            "filename": video_path.name,
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
        },
    }


def _as_float(value, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid numeric field '{field_name}'") from exc


def _safe_optional_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _segment_label(index: int, segment: dict) -> str:
    return f"Segment {index + 1} ({segment.get('name', 'Unnamed')})"


def _ensure_preview_segment_clip(
    project_root: Path,
    project_name: str,
    kind: str,
    segment_index: int,
    source_path: Path,
    trim_start: float,
    duration_sec: float,
) -> str:
    """
    Build a small H.264 preview clip for one segment and return its public URL.

    Using short, downscaled proxies keeps Remotion Studio responsive even when
    source footage is very large or high-framerate.

    Clip filename uses the source video stem so clips from different B-Roll files
    (e.g. broll_main.mp4 vs slap.webm) never collide with each other or with
    A-Roll clips.
    """
    public_dir = project_root / "remotion-src" / "public"
    public_dir.mkdir(parents=True, exist_ok=True)

    safe_project = re.sub(r"[^a-zA-Z0-9_-]", "_", project_name.strip() or "project")
    # Derive clip label from the source video filename stem so that clips from
    # different B-Roll source files (e.g. "broll_main", "slap") never collide.
    clip_label = re.sub(r"[^a-zA-Z0-9_-]", "_", source_path.stem or "clip")
    filename = f"{safe_project}_{clip_label}_seg{segment_index:03d}.mp4"
    target = public_dir / filename

    if target.exists():
        target.unlink()

    trim_start = max(0.0, float(trim_start))
    duration_sec = max(0.05, float(duration_sec))

    cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-v", "error",
        "-ss", f"{trim_start:.6f}",
        "-i", str(source_path),
        "-t", f"{duration_sec:.6f}",
        "-vf", "scale='if(gte(iw,ih),min(1920,iw),min(1080,iw))':'if(gte(iw,ih),-2,min(1920,ih))':flags=lanczos,fps=30",
        "-c:v", "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
    ]

    # Preserve A-Roll audio for Studio preview timing and mix decisions.
    if kind == "aroll":
        cmd.extend([
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
        ])
    else:
        cmd.append("-an")

    cmd.append(str(target))

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            f"Failed to build preview clip {filename}: ffmpeg timed out"
        ) from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ffmpeg failed").strip()
        raise ValueError(f"Failed to build preview clip {filename}: {err}")

    if not target.is_file() or target.stat().st_size <= 0:
        raise ValueError(f"Failed to build preview clip {filename}: output file is empty")

    return filename


def _probe_video_dimensions(video_path: Path) -> dict[str, int]:
    import json as _json

    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,sample_aspect_ratio,side_data_list",
        "-of", "json",
        str(video_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            f"Failed to probe video dimensions for {video_path.name}: ffprobe timed out"
        ) from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ffprobe failed").strip()
        raise ValueError(
            f"Failed to probe video dimensions for {video_path.name}: {err}"
        )

    data = _json.loads(proc.stdout or "{}")
    streams = data.get("streams", [{}])
    st = streams[0] if streams else {}

    width = int(st.get("width", 0))
    height = int(st.get("height", 0))
    if width <= 0 or height <= 0:
        raise ValueError(
            f"Invalid dimensions for {video_path.name}: {width}x{height}"
        )

    # Correct for non-square pixel aspect ratio (SAR).
    sar = st.get("sample_aspect_ratio", "1:1") or "1:1"
    if sar not in ("1:1", "0:1", ""):
        try:
            sar_x, sar_y = (int(p) for p in sar.split(":"))
            if sar_x > 0 and sar_y > 0 and sar_x != sar_y:
                width = round(width * sar_x / sar_y)
        except (ValueError, ZeroDivisionError):
            pass

    # Correct for rotation metadata. Browsers apply the rotation tag from the
    # container and swap videoWidth/videoHeight for 90° and 270° rotations.
    # ffprobe reports raw stream dimensions, so we must swap here to match what
    # the browser (and the canvas preview) sees via videoEl.videoWidth/videoHeight.
    rotation = 0
    for side_data in st.get("side_data_list", []):
        if side_data.get("side_data_type") == "Display Matrix":
            try:
                rotation = int(side_data.get("rotation", 0))
            except (ValueError, TypeError):
                pass
            break
    if rotation in (90, -90, 270, -270):
        width, height = height, width

    return {"width": width, "height": height}


def _generate_segment_component(index: int, joined: dict) -> str:
    if joined["layout"] == "half_and_half":
        aroll_dims = joined.get("aroll_dims") or {"width": 1080, "height": 1920}
        broll_dims = joined.get("broll_dims") or {"width": 1920, "height": 1080}
        return f'''// AUTO-GENERATED -- do not edit. Re-run via the trimmer UI to update.
import React from "react";
import {{ staticFile }} from "remotion";
import {{ HalfAndHalf }} from "./layouts/HalfAndHalf";

type BubbleTransform = {{ posX: number; posY: number; zoom: number; softness: number }};
type SegmentTransforms = {{
    aroll: {{ zoom: number; posX: number; posY: number }};
    broll: {{ zoom: number; posX: number; posY: number }};
    bubble: BubbleTransform;
}};

export const Segment{index}: React.FC<{{ splitRatio: number; visualTransforms: SegmentTransforms }}> = ({{ splitRatio, visualTransforms }}) => (
  <HalfAndHalf
        arollSrc={{staticFile({json.dumps(joined["aroll_src"])})}}
        brollSrc={{staticFile({json.dumps(joined["broll_src"])})}}
    arollSourceSize={{{{ width: {aroll_dims['width']}, height: {aroll_dims['height']} }}}}
    brollSourceSize={{{{ width: {broll_dims['width']}, height: {broll_dims['height']} }}}}
    arollTrimStart={{{joined["aroll_trim_start"]}}}
    brollTrimStart={{{joined["broll_trim_start"]}}}
    durationSec={{{joined["duration_sec"]}}}
    splitRatio={{splitRatio}}
        arollTransform={{visualTransforms.aroll}}
        brollTransform={{visualTransforms.broll}}
    fps={{{FPS}}}
  />
);
'''

    if joined["layout"] == "broll_only":
        aroll_dims = joined.get("aroll_dims") or {"width": 1080, "height": 1920}
        broll_dims = joined.get("broll_dims") or {"width": 1920, "height": 1080}
        return f'''// AUTO-GENERATED -- do not edit. Re-run via the trimmer UI to update.
import React from "react";
import {{ staticFile }} from "remotion";
import {{ BRollOnly }} from "./layouts/BRollOnly";

type BubbleTransform = {{ posX: number; posY: number; zoom: number; softness: number }};
type SegmentTransforms = {{
    aroll: {{ zoom: number; posX: number; posY: number }};
    broll: {{ zoom: number; posX: number; posY: number }};
    bubble: BubbleTransform;
}};

export const Segment{index}: React.FC<{{ visualTransforms: SegmentTransforms }}> = ({{ visualTransforms }}) => (
    <BRollOnly
        brollSrc={{staticFile({json.dumps(joined["broll_src"])})}}
        arollSrc={{staticFile({json.dumps(joined["aroll_src"])})}}
        brollSourceSize={{{{ width: {broll_dims['width']}, height: {broll_dims['height']} }}}}
        arollSourceSize={{{{ width: {aroll_dims['width']}, height: {aroll_dims['height']} }}}}
        brollTrimStart={{{joined["broll_trim_start"]}}}
        arollTrimStart={{{joined["aroll_trim_start"]}}}
        durationSec={{{joined["duration_sec"]}}}
        brollTransform={{visualTransforms.broll}}
        fps={{{FPS}}}
    />
);
'''

    if joined["layout"] == "broll_bubble":
        aroll_dims = joined.get("aroll_dims") or {"width": 1080, "height": 1920}
        broll_dims = joined.get("broll_dims") or {"width": 1920, "height": 1080}
        return f'''// AUTO-GENERATED -- do not edit. Re-run via the trimmer UI to update.
import React from "react";
import {{ staticFile }} from "remotion";
import {{ BRollBubble }} from "./layouts/BRollBubble";

type BubbleTransform = {{ posX: number; posY: number; zoom: number; softness: number }};
type SegmentTransforms = {{
    aroll: {{ zoom: number; posX: number; posY: number }};
    broll: {{ zoom: number; posX: number; posY: number }};
    bubble: BubbleTransform;
}};

export const Segment{index}: React.FC<{{ visualTransforms: SegmentTransforms }}> = ({{ visualTransforms }}) => (
    <BRollBubble
        brollSrc={{staticFile({json.dumps(joined["broll_src"])})}}
        arollSrc={{staticFile({json.dumps(joined["aroll_src"])})}}
        brollSourceSize={{{{ width: {broll_dims['width']}, height: {broll_dims['height']} }}}}
        arollSourceSize={{{{ width: {aroll_dims['width']}, height: {aroll_dims['height']} }}}}
        brollTrimStart={{{joined["broll_trim_start"]}}}
        arollTrimStart={{{joined["aroll_trim_start"]}}}
        durationSec={{{joined["duration_sec"]}}}
        brollTransform={{visualTransforms.broll}}
        arollTransform={{visualTransforms.aroll}}
        bubbleTransform={{visualTransforms.bubble ?? {{ posX: -270, posY: 700, zoom: 1.0, softness: 0.3 }}}}
        fps={{{FPS}}}
    />
);
'''

    aroll_dims = joined.get("aroll_dims") or {"width": 1080, "height": 1920}
    return f'''// AUTO-GENERATED -- do not edit. Re-run via the trimmer UI to update.
import React from "react";
import {{ staticFile }} from "remotion";
import {{ ARollOnly }} from "./layouts/ARollOnly";

type BubbleTransform = {{ posX: number; posY: number; zoom: number; softness: number }};
type SegmentTransforms = {{
    aroll: {{ zoom: number; posX: number; posY: number }};
    broll: {{ zoom: number; posX: number; posY: number }};
    bubble: BubbleTransform;
}};

export const Segment{index}: React.FC<{{ visualTransforms: SegmentTransforms }}> = ({{ visualTransforms }}) => (
    <ARollOnly
        arollSrc={{staticFile({json.dumps(joined["aroll_src"])})}}
        arollSourceSize={{{{ width: {aroll_dims['width']}, height: {aroll_dims['height']} }}}}
        arollTrimStart={{{joined["aroll_trim_start"]}}}
        durationSec={{{joined["duration_sec"]}}}
        arollTransform={{visualTransforms.aroll}}
        fps={{{FPS}}}
    />
);
'''


def _generate_composition_component(joined_segments: list[dict]) -> str:
    lines = [
        '// AUTO-GENERATED -- do not edit. Re-run via the trimmer UI to update.',
        'import React from "react";',
        'import { Sequence } from "remotion";',
    ]

    for idx in range(len(joined_segments)):
        lines.append(f'import {{ Segment{idx} }} from "./Segment{idx}";')

    lines.extend(
        [
            "",
            f"export const TOTAL_DURATION_FRAMES = {sum(max(1, round(seg['duration_sec'] * FPS)) for seg in joined_segments)};",
            "",
            "type BubbleTransform = { posX: number; posY: number; zoom: number; softness: number };",
            "type SegmentTransforms = {",
            "  aroll: { zoom: number; posX: number; posY: number };",
            "  broll: { zoom: number; posX: number; posY: number };",
            "  bubble: BubbleTransform;",
            "};",
            "",
            "type Props = {",
            "  segments: Array<{ splitRatio: number; visualTransforms: SegmentTransforms }>;",
            "};",
            "",
            "export const MyComposition: React.FC<Props> = ({ segments }) => (",
            "  <>",
        ]
    )

    cumulative_start_sec = 0.0
    for idx, seg in enumerate(joined_segments):
        from_frame = round(cumulative_start_sec * FPS)
        duration_frames = round(seg["duration_sec"] * FPS)
        if duration_frames <= 0:
            duration_frames = 1

        if from_frame == 0:
            lines.append(f"    <Sequence durationInFrames={{{duration_frames}}}>")
        else:
            lines.append(f"    <Sequence from={{{from_frame}}} durationInFrames={{{duration_frames}}}>")
        if seg["layout"] == "half_and_half":
            lines.append(
                f"      <Segment{idx} splitRatio={{segments[{idx}].splitRatio}} visualTransforms={{segments[{idx}].visualTransforms}} />"
            )
        else:
            lines.append(
                f"      <Segment{idx} visualTransforms={{segments[{idx}].visualTransforms}} />"
            )
        lines.append("    </Sequence>")
        cumulative_start_sec += seg["duration_sec"]

    lines.extend(["  </>", ");", ""])
    return "\n".join(lines)


def _write_input_props(output_dir: Path, broll_segments: list[dict]) -> None:
    existing = _load_existing_input_props(output_dir)
    props = build_remotion_input_props_from_broll(broll_segments, existing)
    (output_dir / "inputProps.json").write_text(
        json.dumps(props, ensure_ascii=False, indent=2),
        "utf-8",
    )


def _write_generated_remotion_files(output_dir: Path, joined_segments: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for existing in output_dir.glob("Segment*.tsx"):
        if re.match(r"^Segment\d+\.tsx$", existing.name):
            existing.unlink()

    for idx, seg in enumerate(joined_segments):
        (output_dir / f"Segment{idx}.tsx").write_text(_generate_segment_component(idx, seg), "utf-8")

    (output_dir / "Composition.tsx").write_text(
        _generate_composition_component(joined_segments),
        "utf-8",
    )
    broll_segments = [seg.get("source_broll", {}) for seg in joined_segments]
    _write_input_props(output_dir, broll_segments)


def generate_remotion_components(project_name: str) -> int:
    project_name = str(project_name).strip()
    if not project_name:
        raise ValueError("Missing project name")

    project_root = WORKSPACE
    project_dir = project_root / project_name
    video_dir = project_dir / "video"

    aroll_json_path = video_dir / "aroll_segments.json"
    output_dir = project_root / "remotion-src" / "src"

    if not aroll_json_path.is_file():
        raise ValueError(f"A-roll JSON not found at {aroll_json_path}")

    try:
        aroll_json = json.loads(aroll_json_path.read_text("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    aroll_json = normalize_aroll_json(aroll_json)
    aroll_src_path = project_root / project_name / "video" / str(aroll_json.get("video", ""))
    aroll_segments = aroll_json.get("segments", [])

    # Discover all B-Roll segment JSON files. Sort: broll_main first, then alphabetical.
    broll_json_list: list[tuple[Path, dict]] = []
    for p in sorted(video_dir.glob("*_segments.json")):
        if p.name == "aroll_segments.json":
            continue
        try:
            raw = json.loads(p.read_text("utf-8"))
        except json.JSONDecodeError:
            print(f"Warning: skipping {p.name}: invalid JSON")
            continue
        if str(raw.get("type", "")).lower() == "broll":
            broll_json_list.append((p, normalize_broll_json(raw)))
    broll_json_list.sort(key=lambda x: (0 if "broll_main" in x[0].stem else 1, x[0].name))

    if not broll_json_list:
        raise ValueError(f"No B-roll segment JSON files found in {video_dir}")

    # Validate video files for all B-Roll sources.
    for broll_json_path, broll_json in broll_json_list:
        broll_src = project_root / project_name / "video" / str(broll_json.get("video", ""))
        broll_segs = broll_json.get("segments", [])
        needs_broll_video = any(
            FORMAT_MAP.get(str(s.get("broll_format", "")), FALLBACK_LAYOUT) in ("half_and_half", "broll_only", "broll_bubble")
            for s in broll_segs
            if isinstance(s, dict)
        )
        if needs_broll_video and not broll_src.is_file():
            raise ValueError(f"B-roll video not found at {broll_src}")

    needs_aroll_video = any(
        isinstance(s, dict)
        for _, broll_json in broll_json_list
        for s in broll_json.get("segments", [])
    )
    if needs_aroll_video and not aroll_src_path.is_file():
        raise ValueError(f"A-roll video not found at {aroll_src_path}")

    if not isinstance(aroll_segments, list):
        raise ValueError("Invalid segments structure in A-roll JSON")

    joined_segments: list[dict] = []
    assigned_aroll_indices: set[int] = set()

    # Process each B-Roll file in order.  local_idx is the segment's position within
    # its own file (used for broll clip naming so clips from different files never
    # collide).  aroll clip names are keyed by aroll_segment_index so the preview
    # can look them up directly from the segment's aroll_segment_index field.
    for broll_json_path, broll_json in broll_json_list:
        broll_src_path = project_root / project_name / "video" / str(broll_json.get("video", ""))
        broll_segments = broll_json.get("segments", [])

        for local_idx, bseg in enumerate(broll_segments):
            label = _segment_label(len(joined_segments), bseg)

            format_label = str(bseg.get("broll_format", ""))
            layout = FORMAT_MAP.get(format_label)
            if layout is None:
                print(
                    f"Warning: {label}: unknown broll_format '{format_label}', using fallback '{FALLBACK_LAYOUT}'"
                )
                layout = FALLBACK_LAYOUT

            raw_start = _safe_optional_float(bseg.get("start"))
            raw_end = _safe_optional_float(bseg.get("end"))

            if layout == "broll_only":
                # B-Roll Only: visually full-frame B-roll, audio from the associated A-roll segment.
                if not broll_src_path.is_file():
                    raise ValueError(
                        f"{label}: B-Roll Only requires a B-roll video at {broll_src_path}"
                    )
                # A-roll association is required for audio.
                aroll_idx = bseg.get("aroll_segment_index")
                if not isinstance(aroll_idx, int) or aroll_idx < 0 or aroll_idx >= len(aroll_segments):
                    raise ValueError(
                        f"{label}: B-Roll Only requires a valid aroll_segment_index (got {aroll_idx!r})"
                    )
                assigned_aroll_indices.add(aroll_idx)

                aroll_seg = aroll_segments[aroll_idx]

                # Duration is driven by the A-roll segment (same as Half-And-Half).
                partitions = aroll_seg.get("partitions", [])
                if not isinstance(partitions, list):
                    partitions = []
                if partitions:
                    part_idx = bseg.get("aroll_partition_index")
                    if not isinstance(part_idx, int) or part_idx < 0 or part_idx >= len(partitions):
                        raise ValueError(
                            f"{label}: aroll_partition_index out of bounds ({part_idx})"
                        )
                    part = partitions[part_idx]
                    aroll_trim_start = _as_float(part.get("start"), "partition.start")
                    aroll_trim_end = _as_float(part.get("end"), "partition.end")
                else:
                    aroll_trim_start = _as_float(aroll_seg.get("start"), "aroll.start")
                    aroll_trim_end = _as_float(aroll_seg.get("end"), "aroll.end")

                duration_sec = round(max(0.0, aroll_trim_end - aroll_trim_start), 3)
                if duration_sec <= 0:
                    raise ValueError(f"{label}: A-roll segment has non-positive duration")

                broll_start = max(0.0, float(raw_start)) if raw_start is not None else 0.0

                # Aroll clip keyed by aroll_segment_index so the HTML preview can look it up.
                aroll_public_src = _ensure_preview_segment_clip(
                    project_root=project_root,
                    project_name=project_name,
                    kind="aroll",
                    segment_index=aroll_idx,
                    source_path=aroll_src_path,
                    trim_start=aroll_trim_start,
                    duration_sec=duration_sec,
                )
                # Broll clip keyed by local_idx within this broll file (video stem in name prevents collisions).
                broll_public_src = _ensure_preview_segment_clip(
                    project_root=project_root,
                    project_name=project_name,
                    kind="broll",
                    segment_index=local_idx,
                    source_path=broll_src_path,
                    trim_start=broll_start,
                    duration_sec=duration_sec,
                )
                aroll_dims = _probe_video_dimensions(project_root / "remotion-src" / "public" / aroll_public_src)
                broll_dims = _probe_video_dimensions(project_root / "remotion-src" / "public" / broll_public_src)

                joined_segments.append(
                    {
                        "layout": "broll_only",
                        "aroll_src": aroll_public_src,
                        "broll_src": broll_public_src,
                        "aroll_dims": aroll_dims,
                        "broll_dims": broll_dims,
                        "aroll_trim_start": 0,
                        "broll_trim_start": 0,
                        "duration_sec": duration_sec,
                        "source_broll": bseg,
                    }
                )
                continue

            # For all other layouts, an A-roll segment association is required.
            aroll_idx = bseg.get("aroll_segment_index")
            if not isinstance(aroll_idx, int) or aroll_idx < 0 or aroll_idx >= len(aroll_segments):
                raise ValueError(f"{label}: invalid aroll_segment_index={aroll_idx}")
            assigned_aroll_indices.add(aroll_idx)

            aroll_seg = aroll_segments[aroll_idx]
            max_duration = _as_float(bseg.get("max_duration"), "max_duration")
            if max_duration <= 0:
                raise ValueError(f"{label}: max_duration must be > 0")

            # Legacy/incomplete segment data can omit start/end; derive stable timings
            # from max_duration so generation still succeeds.
            if raw_start is None and raw_end is None:
                broll_start = 0.0
                duration_sec = round(max_duration, 3)
                broll_end = broll_start + duration_sec
                print(
                    f"Warning: {label}: missing start/end, defaulting broll trim to 0s for {duration_sec:.3f}s"
                )
            elif raw_start is not None and raw_end is None:
                broll_start = max(0.0, raw_start)
                duration_sec = round(max_duration, 3)
                broll_end = broll_start + duration_sec
                print(
                    f"Warning: {label}: missing end, deriving from start + max_duration ({duration_sec:.3f}s)"
                )
            elif raw_start is None and raw_end is not None:
                duration_sec = round(max_duration, 3)
                broll_end = max(0.0, raw_end)
                broll_start = max(0.0, broll_end - duration_sec)
                print(
                    f"Warning: {label}: missing start, deriving from end - max_duration ({duration_sec:.3f}s)"
                )
            else:
                broll_start = max(0.0, float(raw_start))
                broll_end = max(broll_start, float(raw_end))
                duration_sec = round(broll_end - broll_start, 3)
                if duration_sec <= 0:
                    duration_sec = round(max_duration, 3)
                    broll_end = broll_start + duration_sec
                    print(
                        f"Warning: {label}: non-positive end-start, using max_duration ({duration_sec:.3f}s)"
                    )
                elif abs(max_duration - duration_sec) > 0.01:
                    print(
                        f"Warning: {label}: max_duration ({max_duration}) != end-start ({duration_sec}); using end-start"
                    )

            partitions = aroll_seg.get("partitions", [])
            if not isinstance(partitions, list):
                partitions = []

            if partitions:
                part_idx = bseg.get("aroll_partition_index")
                if not isinstance(part_idx, int) or part_idx < 0 or part_idx >= len(partitions):
                    raise ValueError(f"{label}: aroll_partition_index out of bounds ({part_idx})")
                part = partitions[part_idx]
                aroll_trim_start = _as_float(part.get("start"), "partition.start")
                _ = _as_float(part.get("end"), "partition.end")
            else:
                aroll_trim_start = _as_float(aroll_seg.get("start"), "aroll.start")
                _ = _as_float(aroll_seg.get("end"), "aroll.end")

            if layout in ("half_and_half", "broll_bubble") and not broll_src_path.is_file():
                raise ValueError(
                    f"{label}: layout is {format_label!r} "
                    f"but B-roll video not found at {broll_src_path}"
                )

            # Aroll clip keyed by aroll_segment_index.
            aroll_public_src = _ensure_preview_segment_clip(
                project_root=project_root,
                project_name=project_name,
                kind="aroll",
                segment_index=aroll_idx,
                source_path=aroll_src_path,
                trim_start=aroll_trim_start,
                duration_sec=duration_sec,
            )

            broll_public_src = ""
            broll_dims = None
            if layout in ("half_and_half", "broll_bubble"):
                # Broll clip keyed by local_idx within this broll file.
                broll_public_src = _ensure_preview_segment_clip(
                    project_root=project_root,
                    project_name=project_name,
                    kind="broll",
                    segment_index=local_idx,
                    source_path=broll_src_path,
                    trim_start=broll_start,
                    duration_sec=duration_sec,
                )
                broll_dims = _probe_video_dimensions(project_root / "remotion-src" / "public" / broll_public_src)

            aroll_dims = _probe_video_dimensions(project_root / "remotion-src" / "public" / aroll_public_src)

            joined_segments.append(
                {
                    "layout": layout,
                    "aroll_src": aroll_public_src,
                    "broll_src": broll_public_src,
                    "aroll_dims": aroll_dims,
                    "broll_dims": broll_dims,
                    "aroll_trim_start": 0,
                    "broll_trim_start": 0,
                    "duration_sec": duration_sec,
                    "source_broll": bseg,
                }
            )

    # Keep A-Roll segments that are not linked by any B-Roll as A-Roll-only
    # clips in the generated composition.  Aroll clips are keyed by their own
    # aroll_idx so the HTML preview can look them up via aroll_segment_index.
    unassigned_added = 0
    for aroll_idx, aroll_seg in enumerate(aroll_segments):
        if aroll_idx in assigned_aroll_indices:
            continue
        if not aroll_src_path.is_file():
            print(f"Info: skipping unassigned aroll segment {aroll_idx}: A-roll video not found")
            continue

        aroll_start = _as_float(aroll_seg.get("start"), "aroll.start")
        aroll_end = _as_float(aroll_seg.get("end"), "aroll.end")
        duration_sec = round(max(0.0, aroll_end - aroll_start), 3)
        if duration_sec <= 0:
            continue

        aroll_public_src = _ensure_preview_segment_clip(
            project_root=project_root,
            project_name=project_name,
            kind="aroll",
            segment_index=aroll_idx,
            source_path=aroll_src_path,
            trim_start=aroll_start,
            duration_sec=duration_sec,
        )
        aroll_dims_unassigned = _probe_video_dimensions(
            project_root / "remotion-src" / "public" / aroll_public_src
        )

        joined_segments.append(
            {
                "layout": "aroll_only",
                "aroll_src": aroll_public_src,
                "broll_src": "",
                "aroll_dims": aroll_dims_unassigned,
                "aroll_trim_start": 0,
                "broll_trim_start": 0,
                "duration_sec": duration_sec,
                "source_broll": {
                    "splitRatio": 0.5,
                    "visual_transforms": normalize_visual_transforms(aroll_seg.get("visual_transforms")),
                },
            }
        )
        unassigned_added += 1

    if unassigned_added:
        print(f"Info: added {unassigned_added} unassigned A-roll segment(s) as A-Roll Only")

    _write_generated_remotion_files(output_dir, joined_segments)

    subprocess.Popen(
        ["npx", "remotion", "studio"],
        cwd=project_root / "remotion-src",
    )

    return len(joined_segments)


# ─── HTTP Handler ───────────────────────────────────────────────────────────
class TrimmerHandler(http.server.BaseHTTPRequestHandler):
    session_store: SessionStore
    on_client_open: callable
    on_client_heartbeat: callable
    on_client_close: callable

    def log_message(self, fmt, *args):  # noqa: ARG002
        pass  # suppress default logging

    def _session(self) -> dict:
        return self.session_store.get()

    def _project_dir(self) -> Path:
        return WORKSPACE / self._session()["project"]

    def _video_filename(self) -> str:
        return self._session()["videoFilename"]

    # ── GET ──────────────────────────────────────────────────────────────
    def do_GET(self):
        req = urlparse(self.path)
        path = req.path
        query = parse_qs(req.query)

        if path == "/":
            self._serve_file(SCRIPT_DIR / "trimmer_ui.html", "text/html; charset=utf-8")
        elif path == "/api/config":
            cfg = self._session()
            cfg["restoredFromBackup"] = self.session_store.restored_from_backup()
            self._json(cfg)
        elif path == "/api/options":
            selected = self._session()
            project = query.get("project", [selected["project"]])[0]
            mode = query.get("mode", [selected["mode"]])[0]
            mode = "aroll" if mode == "aroll" else "broll"
            projects = list_projects()
            self._json(
                {
                    "projects": projects,
                    "modes": ["aroll", "broll"],
                    "videos": build_mode_videos(project, mode) if project in projects else [],
                    "selected": selected,
                    "backupPath": str(SESSION_BACKUP),
                }
            )
        elif path == "/api/segments":
            session = self._session()
            p = segments_path(WORKSPACE / session["project"], session["videoFilename"])
            if p.exists():
                data = json.loads(p.read_text("utf-8"))
            else:
                data = {"segments": []}
            
            # Normalize based on mode to ensure schema compatibility
            if session["mode"] == "aroll":
                data = normalize_aroll_json(data)
            else:
                data = normalize_broll_json(data)
            self._json(data)
        elif path == "/api/aroll-segments":
            p = segments_path(self._project_dir(), "aroll.mp4")
            data = json.loads(p.read_text("utf-8")) if p.exists() else {"segments": []}
            self._json(data)
        elif path == "/api/broll-main-segments":
            session = self._session()
            try:
                broll_data, _ = load_broll_data_for_project(session["project"], "broll_main.mp4")
            except (OSError, json.JSONDecodeError):
                self._json({"segments": []})
                return
            self._json(broll_data)
        elif path == "/api/aroll-used-cross-video":
            # Returns all aroll_segment_index values assigned in OTHER broll segment files
            # (i.e. every broll video except the current one). Used by the UI to prevent
            # the same A-roll segment from being assigned to segments across different videos.
            session = self._session()
            project_dir = WORKSPACE / session["project"] / "video"
            current_video = session["videoFilename"]
            used_indices: set[int] = set()
            if project_dir.is_dir():
                for seg_file in project_dir.glob("*_segments.json"):
                    # Derive the video filename that would produce this segments file.
                    stem = seg_file.stem[: -len("_segments")]  # strip "_segments"
                    # Skip aroll and the current video.
                    if stem in ("aroll",):
                        continue
                    if f"{stem}.mp4" == current_video or f"{stem}.webm" == current_video:
                        continue
                    try:
                        raw = json.loads(seg_file.read_text("utf-8"))
                        for seg in raw.get("segments", []):
                            if not isinstance(seg, dict):
                                continue
                            idx_val = seg.get("aroll_segment_index")
                            if isinstance(idx_val, int) and idx_val >= 0:
                                used_indices.add(idx_val)
                    except (OSError, json.JSONDecodeError):
                        pass
            self._json({"usedIndices": sorted(used_indices)})
        elif path == "/api/ping":
            self._json({"ok": True})
        elif path == "/api/has-audio":
            requested = query.get("video", [self._video_filename()])[0]
            filename = os.path.basename(requested)
            video_path = self._project_dir() / "video" / filename
            if not video_path.is_file():
                self.send_error(404, f"Not found: {filename}")
                return
            self._json({"hasAudio": has_audio_stream(video_path)})
        elif path == "/api/waveform":
            requested = query.get("video", [self._video_filename()])[0]
            filename = os.path.basename(requested)
            project_dir = self._project_dir()
            video_path = project_dir / "video" / filename
            if not video_path.is_file():
                self.send_error(404, f"Not found: {filename}")
                return

            if not has_audio_stream(video_path):
                self._json({"peaks": [], "noAudio": True})
                return

            cache_path = waveform_path(project_dir, filename)
            stat = video_path.stat()
            cached = None
            if cache_path.exists():
                try:
                    cached = json.loads(cache_path.read_text("utf-8"))
                except json.JSONDecodeError:
                    cached = None

            if cached:
                src = cached.get("source", {})
                if src.get("size") == stat.st_size and src.get("mtime") == int(stat.st_mtime):
                    self._json(cached)
                    return

            try:
                data = build_waveform(video_path)
            except RuntimeError as exc:
                self._json({"error": str(exc), "peaks": []}, status=500)
                return

            cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
            self._json(data)
        elif path == "/api/remotion/input-props":
            project_name = str(query.get("project", [self._session()["project"]])[0]).strip()
            if not project_name:
                self._json({"ok": False, "error": "Missing project"}, status=400)
                return
            try:
                broll_data, _ = load_broll_data_for_project(project_name)
            except (OSError, json.JSONDecodeError):
                self._json({"ok": False, "error": "Failed to load B-Roll segments"}, status=500)
                return

            output_dir = WORKSPACE / "remotion-src" / "src"
            existing = _load_existing_input_props(output_dir)
            props = build_remotion_input_props_from_broll(broll_data.get("segments", []), existing)
            self._json({"ok": True, "project": project_name, "inputProps": props})
        elif path == "/api/presets":
            format_name = str(query.get("format", [""])[0]).strip()
            if not format_name:
                self._json({"ok": False, "error": "Missing format"}, status=400)
                return
            presets = read_backup_presets().get(format_name, [])
            self._json({"ok": True, "format": format_name, "presets": presets})
        elif path.startswith("/assets/"):
            self._serve_asset(path[8:])
        elif path.startswith("/video/"):
            self._serve_video(path[7:])
        else:
            self.send_error(404)

    # ── POST ─────────────────────────────────────────────────────────────
    def do_POST(self):
        req_path = urlparse(self.path).path
        if req_path == "/api/segments":
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = json.loads(body)
            session = self._session()
            p = segments_path(WORKSPACE / session["project"], session["videoFilename"])
            if session["mode"] == "aroll":
                data = normalize_aroll_json(data)
            else:
                data = normalize_broll_json(data)
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
            self._json({"ok": True})
        elif req_path == "/api/partitions/update":
            self._handle_partition_update()
        elif req_path == "/api/session":
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = json.loads(body)
            next_session = normalize_session(
                data.get("project", ""),
                data.get("mode", "aroll"),
                data.get("videoFilename", ""),
            )
            ok, msg = validate_session(next_session)
            if not ok:
                self._json({"ok": False, "error": msg}, status=400)
                return
            self.session_store.set(next_session)
            save_backup_session(next_session)
            self._json({"ok": True, "session": next_session})
        elif req_path == "/api/client-open":
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            type(self).on_client_open()
            self._json({"ok": True})
        elif req_path == "/api/client-heartbeat":
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            type(self).on_client_heartbeat()
            self._json({"ok": True})
        elif req_path == "/api/client-close":
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            type(self).on_client_close()
            self._json({"ok": True})
        elif req_path == "/api/segments/visual-transform":
            self._handle_visual_transform_update()
        elif req_path == "/api/segments/visual-transform/bulk":
            self._handle_visual_transform_bulk_update()
        elif req_path == "/api/remotion/input-props/save":
            self._handle_save_remotion_input_props()
        elif req_path == "/api/presets":
            self._handle_create_preset()
        elif req_path == "/api/generate-remotion":
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(body)
            except (ValueError, json.JSONDecodeError):
                self._json({"ok": False, "error": "Invalid JSON body"}, status=400)
                return

            project = str(data.get("project", "")).strip()
            try:
                segment_count = generate_remotion_components(project)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
                return
            except OSError as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
                return

            self._json({"ok": True, "segment_count": segment_count})
        else:
            self.send_error(404)

    def do_DELETE(self):
        req_path = urlparse(self.path).path
        if req_path == "/api/presets":
            self._handle_delete_preset()
            return
        self.send_error(404)

    # ── Response helpers ─────────────────────────────────────────────────
    def _json(self, obj, status: int = 200):
        try:
            raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            # Browser/tab closed mid-response.
            return

    def _handle_partition_update(self):
        """
        Handle partition creation/update for an A-Roll segment.
        
        Request body:
        {
            "aroll_segment_index": 0,
            "partitions": [
                {"name": "Part A", "start": 13.056, "end": 14.0},
                {"name": "Part B", "start": 14.0, "end": 15.023}
            ]
        }
        
        Response: {"ok": true, "updated_broll_segments": [...]}
        """
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            req_data = json.loads(body)
        except (ValueError, json.JSONDecodeError):
            self._json({"ok": False, "error": "Invalid JSON"}, status=400)
            return
        
        session = self._session()
        project_dir = WORKSPACE / session["project"]
        
        # Load current A-Roll segments
        aroll_path = segments_path(project_dir, "aroll.mp4")
        try:
            aroll_data = json.loads(aroll_path.read_text("utf-8")) if aroll_path.exists() else {"segments": []}
            aroll_data = normalize_aroll_json(aroll_data)
        except (OSError, json.JSONDecodeError):
            self._json({"ok": False, "error": "Failed to read A-Roll JSON"}, status=500)
            return
        
        seg_idx = req_data.get("aroll_segment_index")
        if not isinstance(seg_idx, int) or seg_idx < 0 or seg_idx >= len(aroll_data["segments"]):
            self._json({"ok": False, "error": "Invalid segment index"}, status=400)
            return
        
        # Update the segment's partitions
        partitions = req_data.get("partitions", [])
        if not isinstance(partitions, list):
            self._json({"ok": False, "error": "Partitions must be a list"}, status=400)
            return
        
        aroll_data["segments"][seg_idx]["partitions"] = partitions
        
        # Save updated A-Roll
        try:
            aroll_path.write_text(json.dumps(aroll_data, ensure_ascii=False, indent=2), "utf-8")
        except OSError as e:
            self._json({"ok": False, "error": f"Failed to save A-Roll: {e}"}, status=500)
            return
        
        updated_broll_segments: list[dict] = []

        # Update all B-Roll segment files in this project so partitioning stays
        # consistent regardless of which B-Roll clip is currently selected.
        broll_seg_files = sorted(project_dir.glob("video/*_segments.json"))
        broll_seg_files = [p for p in broll_seg_files if p.name != "aroll_segments.json"]

        for broll_path in broll_seg_files:
            try:
                raw = json.loads(broll_path.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            if raw.get("type") != "broll":
                continue

            broll_data = normalize_broll_json(raw)
            segs = broll_data.get("segments", [])
            if not isinstance(segs, list) or not segs:
                continue

            broll_data["segments"] = split_broll_segments_for_aroll_partitions(
                aroll_data["segments"][seg_idx],
                seg_idx,
                segs,
            )

            try:
                broll_path.write_text(json.dumps(broll_data, ensure_ascii=False, indent=2), "utf-8")
            except OSError as e:
                self._json({"ok": False, "error": f"Failed to save B-Roll: {e}"}, status=500)
                return

            # Keep response payload compatible with current UI expectations.
            if broll_path.stem == "broll_main_segments":
                updated_broll_segments = broll_data.get("segments", [])

        self._json({
            "ok": True,
            "updated_broll_segments": updated_broll_segments,
        })

    def _handle_visual_transform_update(self):
        session = self._session()

        req_data = _parse_json_body(self)
        if req_data is None:
            self._json({"ok": False, "error": "Invalid JSON body"}, status=400)
            return

        seg_idx = req_data.get("segmentIndex")
        if not isinstance(seg_idx, int):
            self._json({"ok": False, "error": "segmentIndex must be an integer"}, status=400)
            return

        if session["mode"] == "broll":
            try:
                data, p = load_broll_data_for_project(session["project"], session["videoFilename"])
            except (OSError, json.JSONDecodeError):
                self._json({"ok": False, "error": "Failed to load B-Roll segments"}, status=500)
                return
            segs = data.get("segments", [])
            save_error_label = "B-Roll segments"
        else:
            p = segments_path(WORKSPACE / session["project"], "aroll.mp4")
            if p.exists():
                try:
                    raw = json.loads(p.read_text("utf-8"))
                except (OSError, json.JSONDecodeError):
                    self._json({"ok": False, "error": "Failed to load A-Roll segments"}, status=500)
                    return
            else:
                raw = {
                    "project": session["project"],
                    "type": "aroll",
                    "video": "aroll.mp4",
                    "segments": [],
                }
            data = normalize_aroll_json(raw)
            segs = data.get("segments", [])
            save_error_label = "A-Roll segments"

        if not isinstance(segs, list) or seg_idx < 0 or seg_idx >= len(segs):
            self._json({"ok": False, "error": "segmentIndex out of bounds"}, status=400)
            return

        transforms = normalize_visual_transforms(req_data.get("visualTransforms"))
        segs[seg_idx]["visual_transforms"] = transforms

        try:
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        except OSError as exc:
            self._json({"ok": False, "error": f"Failed to save {save_error_label}: {exc}"}, status=500)
            return

        self._json(
            {
                "ok": True,
                "segmentIndex": seg_idx,
                "segment": segs[seg_idx],
                "savedAt": _utc_now_iso(),
            }
        )

    def _handle_visual_transform_bulk_update(self):
        session = self._session()
        if session["mode"] != "broll":
            self._json({"ok": False, "error": "Bulk visual transform updates are only available in broll mode"}, status=400)
            return

        req_data = _parse_json_body(self)
        if req_data is None:
            self._json({"ok": False, "error": "Invalid JSON body"}, status=400)
            return

        updates = req_data.get("updates")
        if not isinstance(updates, list):
            self._json({"ok": False, "error": "updates must be a list"}, status=400)
            return

        try:
            broll_data, p = load_broll_data_for_project(session["project"], session["videoFilename"])
        except (OSError, json.JSONDecodeError):
            self._json({"ok": False, "error": "Failed to load B-Roll segments"}, status=500)
            return

        segs = broll_data.get("segments", [])
        if not isinstance(segs, list):
            self._json({"ok": False, "error": "Invalid B-Roll segment structure"}, status=500)
            return

        results: list[dict] = []
        updated_any = False
        for item in updates:
            if not isinstance(item, dict):
                results.append({"ok": False, "error": "invalid update payload"})
                continue
            seg_idx = item.get("segmentIndex")
            if not isinstance(seg_idx, int):
                results.append({"segmentIndex": seg_idx, "ok": False, "error": "segmentIndex must be an integer"})
                continue
            if seg_idx < 0 or seg_idx >= len(segs):
                results.append({"segmentIndex": seg_idx, "ok": False, "error": "segmentIndex out of bounds"})
                continue

            transforms = normalize_visual_transforms(item.get("visualTransforms"))
            segs[seg_idx]["visual_transforms"] = transforms
            results.append({"segmentIndex": seg_idx, "ok": True, "segment": segs[seg_idx]})
            updated_any = True

        if updated_any:
            try:
                p.write_text(json.dumps(broll_data, ensure_ascii=False, indent=2), "utf-8")
            except OSError as exc:
                self._json({"ok": False, "error": f"Failed to save B-Roll segments: {exc}"}, status=500)
                return

        self._json(
            {
                "ok": True,
                "results": results,
                "savedAt": _utc_now_iso() if updated_any else None,
            }
        )

    def _handle_save_remotion_input_props(self):
        req_data = _parse_json_body(self)
        if req_data is None:
            self._json({"ok": False, "error": "Invalid JSON body"}, status=400)
            return

        project_name = str(req_data.get("project", self._session()["project"])).strip()
        if not project_name:
            self._json({"ok": False, "error": "Missing project"}, status=400)
            return

        payload = req_data.get("inputProps", req_data)
        segments = payload.get("segments") if isinstance(payload, dict) else None
        if not isinstance(segments, list):
            self._json({"ok": False, "error": "inputProps.segments must be a list"}, status=400)
            return

        try:
            broll_data, p = load_broll_data_for_project(project_name)
        except (OSError, json.JSONDecodeError):
            self._json({"ok": False, "error": "Failed to load B-Roll segments"}, status=500)
            return

        broll_segments = broll_data.get("segments", [])
        if not isinstance(broll_segments, list):
            self._json({"ok": False, "error": "Invalid B-Roll segment structure"}, status=500)
            return

        updated = 0
        failures: list[dict] = []
        for idx, seg in enumerate(segments):
            if not isinstance(seg, dict):
                failures.append({"segmentIndex": idx, "error": "Segment entry must be an object"})
                continue
            seg_idx = seg.get("index")
            if not isinstance(seg_idx, int):
                seg_idx = idx
            if seg_idx < 0 or seg_idx >= len(broll_segments):
                failures.append({"segmentIndex": seg_idx, "error": "segment index out of bounds"})
                continue

            broll_segments[seg_idx]["splitRatio"] = normalize_split_ratio(seg.get("splitRatio"), 0.5)
            transforms = seg.get("visualTransforms", seg.get("visual_transforms"))
            broll_segments[seg_idx]["visual_transforms"] = normalize_visual_transforms(transforms)
            updated += 1

        try:
            p.write_text(json.dumps(broll_data, ensure_ascii=False, indent=2), "utf-8")
        except OSError as exc:
            self._json({"ok": False, "error": f"Failed to save B-Roll segments: {exc}"}, status=500)
            return

        self._json(
            {
                "ok": True,
                "project": project_name,
                "updated": updated,
                "failures": failures,
                "savedAt": _utc_now_iso(),
            }
        )

    def _handle_create_preset(self):
        req_data = _parse_json_body(self)
        if req_data is None:
            self._json({"ok": False, "error": "Invalid JSON body"}, status=400)
            return

        format_name = str(req_data.get("format", "")).strip()
        name = str(req_data.get("name", "")).strip()
        if not format_name:
            self._json({"ok": False, "error": "Missing format"}, status=400)
            return
        if not name:
            self._json({"ok": False, "error": "Missing preset name"}, status=400)
            return

        presets = read_backup_presets()
        format_presets = presets.get(format_name, [])
        if any(str(p.get("name", "")).strip() == name for p in format_presets):
            self._json({"ok": False, "error": "Preset name already exists"}, status=409)
            return

        preset = {
            "name": name,
            "aroll": _normalize_layer_transform(req_data.get("aroll")),
            "broll": _normalize_layer_transform(req_data.get("broll")),
            "createdAt": _utc_now_iso(),
        }
        format_presets.append(preset)
        presets[format_name] = format_presets
        write_backup_presets(presets)

        self._json({"ok": True, "format": format_name, "preset": preset, "presets": format_presets})

    def _handle_delete_preset(self):
        req_data = _parse_json_body(self)
        if req_data is None:
            self._json({"ok": False, "error": "Invalid JSON body"}, status=400)
            return

        format_name = str(req_data.get("format", "")).strip()
        name = str(req_data.get("name", "")).strip()
        if not format_name:
            self._json({"ok": False, "error": "Missing format"}, status=400)
            return
        if not name:
            self._json({"ok": False, "error": "Missing preset name"}, status=400)
            return

        presets = read_backup_presets()
        format_presets = presets.get(format_name, [])
        if not isinstance(format_presets, list):
            format_presets = []

        kept = [p for p in format_presets if str(p.get("name", "")).strip() != name]
        if len(kept) == len(format_presets):
            self._json({"ok": False, "error": "Preset not found"}, status=404)
            return

        presets[format_name] = kept
        write_backup_presets(presets)
        self._json({"ok": True, "format": format_name, "name": name, "presets": kept})

    def _serve_file(self, filepath: Path, content_type: str):
        try:
            content = filepath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _serve_video(self, filename: str):
        # Sanitise – prevent path traversal
        filename = os.path.basename(filename)
        video_path = self._project_dir() / "video" / filename
        if not video_path.is_file():
            # Generated segment preview clips live in remotion-src/public.
            remotion_public_path = WORKSPACE / "remotion-src" / "public" / filename
            if remotion_public_path.is_file():
                video_path = remotion_public_path
        if not video_path.is_file():
            self.send_error(404, f"Not found: {filename}")
            return

        size = video_path.stat().st_size
        ctype = mimetypes.guess_type(str(video_path))[0] or "video/mp4"

        try:
            # HTTP Range support (required for video seeking)
            range_hdr = self.headers.get("Range")
            if range_hdr:
                m = re.match(r"bytes=(\d+)-(\d*)", range_hdr)
                if m:
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                    end = min(end, size - 1)
                    length = end - start + 1

                    self.send_response(206)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    self.send_header("Content-Length", str(length))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()

                    with open(video_path, "rb") as f:
                        f.seek(start)
                        remaining = length
                        while remaining > 0:
                            chunk = f.read(min(65536, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                    return

            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with open(video_path, "rb") as f:
                while chunk := f.read(65536):
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _serve_asset(self, rel_path: str):
        rel_path = (rel_path or "").strip("/")
        if not rel_path:
            self.send_error(404, "Asset path is required")
            return

        base_dir = WORKSPACE / "assets"
        asset_path = (base_dir / rel_path).resolve()

        try:
            asset_path.relative_to(base_dir.resolve())
        except ValueError:
            self.send_error(403, "Forbidden")
            return

        if not asset_path.is_file():
            self.send_error(404, f"Not found: {rel_path}")
            return

        ctype = mimetypes.guess_type(str(asset_path))[0] or "application/octet-stream"
        self._serve_file(asset_path, ctype)


# ─── Main ───────────────────────────────────────────────────────────────────
def main():
    loaded_backup = load_backup_session()
    session = loaded_backup or choose_default_session()
    restored_from_backup = loaded_backup is not None
    ok, msg = validate_session(session)
    if not ok:
        print(f"Backup session ignored: {msg}")
        session = choose_default_session()
        restored_from_backup = False

    save_backup_session(session)
    store = SessionStore(session, restored_from_backup=restored_from_backup)

    shutdown_once = threading.Event()
    client_state = {
        "connected": False,
        "last_seen": 0.0,
    }
    state_lock = threading.Lock()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), TrimmerHandler)

    def initiate_shutdown(reason: str) -> None:
        if shutdown_once.is_set():
            return
        shutdown_once.set()
        print(f"\nStopping server ({reason})...")
        threading.Thread(target=server.shutdown, daemon=True).start()

    def client_open() -> None:
        with state_lock:
            client_state["connected"] = True
            client_state["last_seen"] = time.time()

    def client_heartbeat() -> None:
        with state_lock:
            client_state["last_seen"] = time.time()

    def client_close() -> None:
        with state_lock:
            client_state["connected"] = False
        initiate_shutdown("browser tab closed")

    def watchdog() -> None:
        while not shutdown_once.is_set():
            time.sleep(2)
            with state_lock:
                connected = client_state["connected"]
                last_seen = client_state["last_seen"]
            if connected and (time.time() - last_seen) > 15:
                initiate_shutdown("lost browser heartbeat")
                break

    TrimmerHandler.session_store = store
    TrimmerHandler.on_client_open = client_open
    TrimmerHandler.on_client_heartbeat = client_heartbeat
    TrimmerHandler.on_client_close = client_close

    url = f"http://127.0.0.1:{PORT}"
    current = store.get()
    print(f"\n✓ Serving at {url}")
    print(f"  Project : {current['project']}")
    print(f"  Mode    : {current['mode']}")
    print(f"  Video   : {current['videoFilename']}")
    print(f"  Backup  : {SESSION_BACKUP}")
    print(f"  Ctrl+C to stop\n")

    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    threading.Thread(target=watchdog, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        initiate_shutdown("keyboard interrupt")
    finally:
        server.server_close()
        print("Stopped.")


if __name__ == "__main__":
    main()
