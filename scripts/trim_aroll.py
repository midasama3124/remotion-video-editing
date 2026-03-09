#!/usr/bin/env python3
"""
A-Roll Trimmer
==============
Splits a continuous A-Roll recording into individual takes per script line.

The speaker records the script sequentially, repeating each line multiple
times before moving on.  This script:
  1. Transcribes the A-Roll with Whisper (Spanish)
    2. Adds line metadata directly to transcription segments
    3. Selects the best segment per script line
    4. Trims the video into line<N>-1.mp4 files

Requirements
------------
  pip install faster-whisper          # recommended
  # — OR on Apple Silicon —
  pip install mlx-whisper

  ffmpeg must be on PATH  (brew install ffmpeg)

Configuration constants are at the top of the file — tweak them if matching
quality is poor or takes are being merged/split incorrectly.
"""

import json
import re
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

# ─── Configuration ──────────────────────────────────────────────────────────
WHISPER_MODEL = "large-v3"  # tiny|base|small|medium|large-v3 (smaller = faster)
LANGUAGE = "es"

MATCH_THRESHOLD = 0.45  # min similarity to keep a take
MAX_SEGMENT_DURATION_SECONDS = 8.0  # split longer Whisper segments into chunks
PREFERRED_TAKE_DURATION_SECONDS = 6.0  # bias toward shorter clips per line

TRIM_PAD_BEFORE = 0.15  # seconds of padding before speech
TRIM_PAD_AFTER = 0.10  # seconds of padding after speech

WORKSPACE = Path(__file__).resolve().parent.parent


# ─── Text helpers ───────────────────────────────────────────────────────────
def normalize(text: str) -> str:
    """Lowercase, strip punctuation (keep Spanish chars), collapse spaces."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\sáéíóúñü]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def sim(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


# ─── Transcription back-ends ───────────────────────────────────────────────
def _transcribe_faster_whisper(path: str) -> list[dict]:
    from faster_whisper import WhisperModel

    print(f"  backend: faster-whisper")
    model = WhisperModel(WHISPER_MODEL, compute_type="auto")
    segs, _ = model.transcribe(
        path,
        language=LANGUAGE,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    return [
        {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()}
        for s in segs
    ]


def _transcribe_mlx_whisper(path: str) -> list[dict]:
    import mlx_whisper

    print(f"  backend: mlx-whisper  (Apple Silicon)")
    result = mlx_whisper.transcribe(
        path,
        path_or_hf_repo=f"mlx-community/whisper-{WHISPER_MODEL}-mlx",
        language=LANGUAGE,
    )
    return [
        {
            "start": round(s["start"], 3),
            "end": round(s["end"], 3),
            "text": s["text"].strip(),
        }
        for s in result.get("segments", [])
    ]


def write_cache(aroll_path: Path, transcription_segments: list[dict]):
    """Write cache with transcription segments (including line metadata)."""
    cache = aroll_path.parent / "aroll_transcription.json"
    payload = {"transcription_segments": transcription_segments}
    cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  cached → {cache.name}")


def transcribe(aroll_path: Path) -> list[dict]:
    """Try available Whisper backends; return segments."""
    print(f"\nLoading Whisper model '{WHISPER_MODEL}' …")

    backends = [
        ("faster_whisper", _transcribe_faster_whisper),
        ("mlx_whisper", _transcribe_mlx_whisper),
    ]

    for mod_name, func in backends:
        try:
            __import__(mod_name)
        except ImportError:
            continue

        print(f"Transcribing {aroll_path.name}  (may take several minutes) …\n")
        segments = func(str(aroll_path))

        for s in segments:
            m, sec = divmod(s["start"], 60)
            print(f"  [{int(m):02d}:{sec:05.2f}]  {s['text']}")

        print(f"\n✓ {len(segments)} segments transcribed")

        # Cache raw transcription immediately; line metadata is filled later.
        write_cache(aroll_path, segments)
        return segments

    # No backend found
    print(
        "\n╔═══════════════════════════════════════════════════════════╗\n"
        "║  No Whisper backend found.  Install ONE of:              ║\n"
        "║    pip install faster-whisper                             ║\n"
        "║    pip install mlx-whisper      (Apple Silicon)           ║\n"
        "╚═══════════════════════════════════════════════════════════╝"
    )
    sys.exit(1)


def load_cache(aroll_path: Path) -> dict | list[dict] | None:
    cache = aroll_path.parent / "aroll_transcription.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    return None


def extract_transcription_segments(cache_data: dict | list[dict]) -> list[dict]:
    """Support both old cache format (list) and new object format."""
    if isinstance(cache_data, list):
        return cache_data
    if isinstance(cache_data, dict):
        if isinstance(cache_data.get("transcription_segments"), list):
            return cache_data["transcription_segments"]
    return []


# ─── Script reading ────────────────────────────────────────────────────────
def read_script(path: Path) -> list[str]:
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def split_long_segments(segments: list[dict]) -> list[dict]:
    """Split overly long Whisper segments into smaller chunks.

    Uses punctuation boundaries and allocates timestamps proportionally by
    chunk text length to avoid keeping multi-line merged regions.
    """
    out: list[dict] = []
    for seg in segments:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        text = str(seg.get("text", "")).strip()
        duration = max(0.0, end - start)

        if not text or duration <= MAX_SEGMENT_DURATION_SECONDS:
            out.append(dict(seg))
            continue

        # Split by punctuation and conjunction-like pauses common in Spanish speech.
        chunks = [
            c.strip()
            for c in re.split(r"(?<=[\.!\?;,…])\s+|\s+(?=pero\s|y\s|o\s|porque\s|que\s)", text, flags=re.IGNORECASE)
            if c.strip()
        ]

        # If no meaningful split was found, keep original segment.
        if len(chunks) <= 1:
            out.append(dict(seg))
            continue

        total_chars = sum(max(1, len(c)) for c in chunks)
        cursor = start
        for i, chunk in enumerate(chunks):
            portion = max(1, len(chunk)) / total_chars
            chunk_dur = duration * portion
            chunk_start = cursor
            chunk_end = end if i == len(chunks) - 1 else min(end, cursor + chunk_dur)
            cursor = chunk_end

            new_seg = dict(seg)
            new_seg["start"] = round(chunk_start, 3)
            new_seg["end"] = round(chunk_end, 3)
            new_seg["text"] = chunk
            # Keep original metadata if present (trimmed/line_number/etc.)
            out.append(new_seg)

    return out


# ─── Matching ──────────────────────────────────────────────────────────────
def best_line_match(
    text: str, lines: list[str], cursor: int
) -> tuple[int, float]:
    """
    Find the best-matching single script line for a segment.
    Returns (line_idx, score).
    Biased toward cursor position (sequential recording assumption).
    """
    lo = max(0, cursor - 1)
    best = (cursor, 0.0)

    for start in range(lo, len(lines)):
        score = sim(text, lines[start])
        # Sequential bias
        if start == cursor:
            score += 0.03
        elif start == cursor + 1:
            score += 0.015
        if score > best[1]:
            best = (start, score)

    return best


def annotate_segments_with_lines(
    segments: list[dict], lines: list[str], keep_existing: bool
) -> list[dict]:
    """Add line_number, match_score and trimmed fields inside transcription segments."""
    cursor = 0
    print("\n─── Matching segments → script lines ───────────────────\n")

    annotated: list[dict] = []
    for seg in segments:
        out = dict(seg)
        out["trimmed"] = bool(out.get("trimmed", False))

        if keep_existing and isinstance(out.get("line_number"), int):
            line_number = out["line_number"]
            if 1 <= line_number <= len(lines):
                score = sim(str(out.get("text", "")), lines[line_number - 1])
            else:
                line_number = None
                score = 0.0
            out["line_number"] = line_number
            out["match_score"] = round(float(out.get("match_score", score)), 3)
            annotated.append(out)
            continue

        li, score = best_line_match(str(out.get("text", "")), lines, cursor)
        if li >= cursor:
            cursor = li

        out["line_number"] = li + 1
        out["match_score"] = round(score, 3)
        annotated.append(out)

        state = "✓" if score >= MATCH_THRESHOLD else "⚠"
        print(
            f"  {state} Line {li + 1:<3} score={score:.2f}  "
            f"[{out.get('start', 0):.1f}s–{out.get('end', 0):.1f}s]"
        )
        print(f"    heard:  \"{str(out.get('text', ''))[:100]}\"")
        print(f"    script: \"{lines[li][:100]}\"")
        print()

    return annotated


def filter_segments_for_script(
    segments: list[dict], lines: list[str]
) -> list[dict]:
    """
    Keep only script-relevant segments:
    - Keep all close matches (score >= MATCH_THRESHOLD)
    - Guarantee at least one kept segment per script line (best-score fallback)
    """
    if not segments:
        return []

    enriched: list[dict] = []
    for seg in segments:
        out = dict(seg)
        line_number = out.get("line_number")
        if isinstance(line_number, int) and 1 <= line_number <= len(lines):
            score = sim(str(out.get("text", "")), lines[line_number - 1])
        else:
            line_number = None
            score = 0.0
        out["line_number"] = line_number
        out["match_score"] = round(float(out.get("match_score", score)), 3)
        out["trimmed"] = bool(out.get("trimmed", False))
        enriched.append(out)

    kept: list[dict] = [s for s in enriched if s["line_number"] is not None and s["match_score"] >= MATCH_THRESHOLD]

    # Ensure at least one segment per script line (fallback to best score).
    present_lines = {int(s["line_number"]) for s in kept}
    for idx, line in enumerate(lines, start=1):
        if idx in present_lines:
            continue

        candidates_same_line = [s for s in enriched if s.get("line_number") == idx]
        if candidates_same_line:
            chosen = max(candidates_same_line, key=lambda s: float(s.get("match_score", 0.0)))
            fallback = dict(chosen)
        else:
            # Extreme fallback: pick the globally best segment for this line and relabel it.
            chosen = max(enriched, key=lambda s: sim(str(s.get("text", "")), line))
            fb_score = sim(str(chosen.get("text", "")), line)
            fallback = dict(chosen)
            fallback["line_number"] = idx
            fallback["match_score"] = round(fb_score, 3)

        fallback["forced_line_fallback"] = True
        kept.append(fallback)

    kept.sort(key=lambda s: (int(s.get("line_number", 10**9)), float(s.get("start", 0.0))))
    return kept


def select_best_takes_from_segments(
    segments: list[dict], lines: list[str]
) -> dict[str, dict]:
    """Pick one best segment per line, trimming directly from segment timestamps."""
    untrimmed = [s for s in segments if not s.get("trimmed", False)]
    if not untrimmed:
        return {}

    by_line: dict[int, list[dict]] = {}
    for seg in untrimmed:
        line_number = seg.get("line_number")
        if isinstance(line_number, int) and 1 <= line_number <= len(lines):
            by_line.setdefault(line_number, []).append(seg)

    takes: dict[str, dict] = {}

    def candidate_rank(seg: dict, line_text: str) -> float:
        score = float(seg.get("match_score", sim(str(seg.get("text", "")), line_text)))
        dur = max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))
        # Penalize very long clips so we avoid merged multi-line takes.
        duration_penalty = max(0.0, dur - PREFERRED_TAKE_DURATION_SECONDS) * 0.04
        return score - duration_penalty

    for idx, line in enumerate(lines, start=1):
        candidates = by_line.get(idx, [])
        if candidates:
            chosen = max(candidates, key=lambda s: candidate_rank(s, line))
            takes[str(idx)] = {
                "start": float(chosen["start"]),
                "end": float(chosen["end"]),
                "text": str(chosen.get("text", "")),
                "score": round(float(chosen.get("match_score", sim(str(chosen.get("text", "")), line))), 3),
                "fallback": False,
            }
            continue

        # Fallback: no segment assigned to this line; pick globally best remaining segment.
        fallback = max(untrimmed, key=lambda s: candidate_rank(s, line))
        fb_score = sim(str(fallback.get("text", "")), line)
        takes[str(idx)] = {
            "start": float(fallback["start"]),
            "end": float(fallback["end"]),
            "text": str(fallback.get("text", "")),
            "score": round(fb_score, 3),
            "fallback": True,
        }

    return takes


# ─── Trimming ──────────────────────────────────────────────────────────────
def trim_clip(src: Path, dst: Path, start: float, end: float, *, exact: bool = False) -> bool:
    if exact:
        s = max(0.0, start)
        dur = end - s
    else:
        s = max(0.0, start - TRIM_PAD_BEFORE)
        dur = (end + TRIM_PAD_AFTER) - s
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel", "error",
        "-ss", f"{s:.3f}",
        "-i", str(src),
        "-t", f"{dur:.3f}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        str(dst),
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0


# ─── UI segment backup helpers ─────────────────────────────────────────────
def ui_segments_path(project_dir: Path, video_filename: str) -> Path:
    """Return the path to the UI segment backup file for a given video."""
    stem = Path(video_filename).stem
    return project_dir / "video" / f"{stem}_segments.json"


def trim_from_ui_segments(proj: Path) -> bool:
    """Load UI segment backup files and trim A-Roll + all B-Roll videos.

    Returns True if UI segments were found and processed, False otherwise.
    """
    aroll_seg_path = ui_segments_path(proj, "aroll.mp4")
    if not aroll_seg_path.exists():
        return False

    aroll = proj / "video" / "aroll.mp4"
    if not aroll.exists():
        print(f"Error: A-Roll not found → {aroll}")
        return False

    aroll_data = json.loads(aroll_seg_path.read_text(encoding="utf-8"))
    aroll_segments = aroll_data.get("segments", [])

    if not aroll_segments:
        print("No A-Roll segments found in UI backup file.")
        return False

    out_dir = proj / "video" / "trimmed"
    out_dir.mkdir(exist_ok=True)

    # ── Trim A-Roll ──────────────────────────────────────────────────────
    print(f"\n{'═' * 60}")
    print(f"  A-Roll: {len(aroll_segments)} segments (from UI backup)")
    print(f"{'═' * 60}\n")

    aroll_ok = 0
    for i, seg in enumerate(aroll_segments):
        line_num = i + 1
        start = seg.get("start")
        end = seg.get("end")
        if start is None or end is None:
            print(f"  line{line_num}-1.mp4 … skipped (no start/end)")
            continue
        fname = f"line{line_num}-1.mp4"
        dst = out_dir / fname
        dur = end - start
        print(f"  {fname}  [{start:.3f}s → {end:.3f}s]  ({dur:.3f}s) …", end=" ", flush=True)
        if trim_clip(aroll, dst, start, end, exact=True):
            print("✓")
            aroll_ok += 1
        else:
            print("✗ FAILED")

    print(f"\n✓ A-Roll: {aroll_ok}/{len(aroll_segments)} clips trimmed")

    # ── Trim B-Roll ──────────────────────────────────────────────────────
    broll_files = sorted(proj.glob("video/*_segments.json"))
    broll_files = [f for f in broll_files if f.name != "aroll_segments.json"]

    for broll_seg_path in broll_files:
        broll_data = json.loads(broll_seg_path.read_text(encoding="utf-8"))
        if broll_data.get("type") != "broll":
            continue

        broll_video_name = broll_data.get("video", "")
        broll_video = proj / "video" / broll_video_name
        broll_segments = broll_data.get("segments", [])

        if not broll_video.is_file():
            print(f"\n⚠ B-Roll video not found: {broll_video_name}")
            continue

        if not broll_segments:
            continue

        broll_stem = Path(broll_video_name).stem
        print(f"\n{'═' * 60}")
        print(f"  B-Roll: {broll_video_name} ({len(broll_segments)} segments)")
        print(f"{'═' * 60}\n")

        broll_ok = 0
        for j, seg in enumerate(broll_segments):
            start = seg.get("start")
            end = seg.get("end")
            if start is None or end is None:
                continue
            aroll_idx = seg.get("aroll_segment_index")
            if aroll_idx is not None and 0 <= aroll_idx < len(aroll_segments):
                line_ref = aroll_idx + 1
                fname = f"{broll_stem}_line{line_ref}.mp4"
            else:
                fname = f"{broll_stem}_seg{j + 1}.mp4"
            dst = out_dir / fname
            dur = end - start
            print(f"  {fname}  [{start:.3f}s → {end:.3f}s]  ({dur:.3f}s) …", end=" ", flush=True)
            if trim_clip(broll_video, dst, start, end, exact=True):
                print("✓")
                broll_ok += 1
            else:
                print("✗ FAILED")

        print(f"\n✓ B-Roll {broll_video_name}: {broll_ok}/{len(broll_segments)} clips trimmed")

    print(f"\n  output → {out_dir.relative_to(WORKSPACE)}/")
    return True


# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    project = input("Project name (e.g. honor_robot_phone): ").strip()
    if not project:
        sys.exit("Error: empty project name.")

    proj = WORKSPACE / project
    aroll = proj / "video" / "aroll.mp4"
    script_file = proj / "script.txt"

    for label, p in [("Project dir", proj), ("A-Roll", aroll), ("Script", script_file)]:
        if not p.exists():
            sys.exit(f"Error: {label} not found → {p}")

    # ── Check for UI segment backups ─────────────────────────────────────
    if ui_segments_path(proj, "aroll.mp4").exists():
        ans = input(
            "\nUI segment backup found. Use it for trimming? [Y/n] "
        ).strip().lower()
        if ans != "n":
            trim_from_ui_segments(proj)
            return

    # ── Read script ──────────────────────────────────────────────────────
    lines = read_script(script_file)
    print(f"\nScript  ({len(lines)} lines):")
    for i, l in enumerate(lines, 1):
        print(f"  {i:>2}. {l}")

    # ── Transcribe or load cache ─────────────────────────────────────────
    cached = load_cache(aroll)
    if cached:
        ans = input(
            "\nCached transcription found.  Use it? [Y/n] "
        ).strip().lower()
        if ans != "n":
            segments = extract_transcription_segments(cached)
        else:
            segments = transcribe(aroll)
    else:
        segments = transcribe(aroll)

    if not segments:
        sys.exit("No speech detected in A-Roll.")

    segments = split_long_segments(segments)

    has_line_numbers = any(isinstance(s.get("line_number"), int) for s in segments)
    keep_existing = has_line_numbers and (
        input("\nUse existing line_number values in transcription_segments? [Y/n] ")
        .strip()
        .lower()
        != "n"
    )

    segments = annotate_segments_with_lines(segments, lines, keep_existing=keep_existing)
    segments = filter_segments_for_script(segments, lines)
    write_cache(aroll, segments)

    takes = select_best_takes_from_segments(segments, lines)
    if not takes:
        sys.exit("No untrimmed segments available for trimming.")

    # ── Summary ──────────────────────────────────────────────────────────
    total = len(takes)
    print(f"{'═' * 60}")
    print(f"  {total} selected takes  •  {len(takes)} script line(s)")
    print(f"{'═' * 60}")

    for key in sorted(takes, key=lambda k: int(k)):
        t = takes[key]
        d = t["end"] - t["start"]
        fallback_note = "  [fallback]" if t.get("fallback") else ""
        print(f"\n  Line {key}  (1 take)")
        print(
            f"    1. [{t['start']:.1f}s – {t['end']:.1f}s]  {d:.1f}s  "
            f"score={t['score']}{fallback_note}"
        )

    # ── Confirm ──────────────────────────────────────────────────────────
    if input(f"\nTrim {total} clips? [Y/n] ").strip().lower() == "n":
        sys.exit("Aborted.")

    # ── Trim clips ───────────────────────────────────────────────────────
    out_dir = proj / "video" / "trimmed"
    out_dir.mkdir(exist_ok=True)

    ok = 0
    skipped = 0
    manifest: dict[str, dict] = {}
    trimmed_lines = {
        int(s["line_number"])
        for s in segments
        if s.get("trimmed") is True and isinstance(s.get("line_number"), int)
    }

    for key in sorted(takes, key=lambda k: int(k)):
        line_num = int(key)
        if line_num in trimmed_lines:
            print(f"  line{key}-1.mp4 … skipped (marked trimmed=true in JSON)")
            skipped += 1
            continue
        t = takes[key]
        fname = f"line{key}-1.mp4"
        dst = out_dir / fname
        print(f"  {fname} …", end=" ", flush=True)
        if trim_clip(aroll, dst, t["start"], t["end"]):
            print("✓")
            ok += 1
            manifest[fname] = t
        else:
            print("✗ FAILED")

    # ── Write manifest ───────────────────────────────────────────────────
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    print(f"\n✓ {ok}/{total} clips trimmed  •  {skipped} skipped")
    print(f"  output    → {out_dir.relative_to(WORKSPACE)}/")
    print(f"  manifest  → {manifest_path.relative_to(WORKSPACE)}")


if __name__ == "__main__":
    main()
