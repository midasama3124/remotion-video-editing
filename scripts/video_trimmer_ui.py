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
            data = json.loads(p.read_text("utf-8")) if p.exists() else {"segments": []}
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
