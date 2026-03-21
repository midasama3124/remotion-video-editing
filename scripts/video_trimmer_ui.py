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
        normalized_seg = {
            "name": seg.get("name", "Unnamed"),
            "start": seg.get("start"),
            "end": seg.get("end"),
            "aroll_segment_index": seg.get("aroll_segment_index"),
            "aroll_segment_name": seg.get("aroll_segment_name"),
            "max_duration": seg.get("max_duration"),
            "broll_format": seg.get("broll_format", "Half-And-Half Split"),
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
    if not SESSION_BACKUP.exists():
        return None
    try:
        data = json.loads(SESSION_BACKUP.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return normalize_session(
        data.get("project", ""),
        data.get("mode", "aroll"),
        data.get("videoFilename", ""),
    )


def save_backup_session(session: dict) -> None:
    SESSION_BACKUP.write_text(json.dumps(session, ensure_ascii=False, indent=2), "utf-8")


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
        else:
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
