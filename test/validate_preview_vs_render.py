#!/usr/bin/env python3
"""Build a preview-reference render and compare it frame-by-frame with Remotion output.

Usage:
  python3 scripts/validate_preview_vs_render.py [--save-frames] [--remotion-output PATH]

Options:
  --save-frames        Save PNG side-by-side frames for each segment (frame 0 and
                       the frame with highest MAE) into out/frames/.
  --remotion-output    Path to the Remotion-rendered mp4 (default: out/remotion_after_fix.mp4).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "remotion-src" / "src"
PUBLIC_DIR = ROOT / "remotion-src" / "public"
OUT_DIR = ROOT / "out"

COMPOSITION_WIDTH = 1080
COMPOSITION_HEIGHT = 1920
FPS = 30


@dataclass
class VideoSize:
    width: int
    height: int


@dataclass
class Transform:
    zoom: float
    pos_x: float
    pos_y: float


@dataclass
class SegmentSpec:
    index: int
    layout: str  # "half_and_half" | "aroll_only"
    aroll_src: str
    broll_src: str | None
    aroll_size: VideoSize
    broll_size: VideoSize | None
    duration_sec: float


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def parse_segment_file(path: Path) -> SegmentSpec:
    txt = path.read_text("utf-8")
    idx_match = re.search(r"Segment(\d+)", path.stem)
    if not idx_match:
        raise ValueError(f"Unable to parse segment index from {path.name}")
    index = int(idx_match.group(1))

    layout = "half_and_half" if "HalfAndHalf" in txt else "aroll_only"

    aroll_src = re.search(r'arollSrc=\{staticFile\("([^"]+)"\)\}', txt)
    if not aroll_src:
        raise ValueError(f"Missing arollSrc in {path.name}")

    broll_src_match = re.search(r'brollSrc=\{staticFile\("([^"]+)"\)\}', txt)

    aroll_size_match = re.search(r"arollSourceSize=\{\{ width: (\d+), height: (\d+) \}\}", txt)
    if not aroll_size_match:
        raise ValueError(f"Missing arollSourceSize in {path.name}")

    broll_size_match = re.search(r"brollSourceSize=\{\{ width: (\d+), height: (\d+) \}\}", txt)

    duration_match = re.search(r"durationSec=\{([0-9.]+)\}", txt)
    if not duration_match:
        raise ValueError(f"Missing durationSec in {path.name}")

    return SegmentSpec(
        index=index,
        layout=layout,
        aroll_src=aroll_src.group(1),
        broll_src=broll_src_match.group(1) if broll_src_match else None,
        aroll_size=VideoSize(int(aroll_size_match.group(1)), int(aroll_size_match.group(2))),
        broll_size=VideoSize(int(broll_size_match.group(1)), int(broll_size_match.group(2)))
        if broll_size_match
        else None,
        duration_sec=float(duration_match.group(1)),
    )


def load_specs() -> list[SegmentSpec]:
    specs: list[SegmentSpec] = []
    for p in sorted(
        SRC_DIR.glob("Segment*.tsx"),
        key=lambda f: int(re.search(r"(\d+)", f.stem).group(1)),
    ):
        specs.append(parse_segment_file(p))
    return specs


def read_video_frames(path: Path, expected_frames: int) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")

    frames: list[np.ndarray] = []
    while len(frames) < expected_frames:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)

    cap.release()

    if not frames:
        raise RuntimeError(f"No frames read from {path}")

    while len(frames) < expected_frames:
        frames.append(frames[-1].copy())

    return frames[:expected_frames]


def blit_cover_with_transform(
    canvas: np.ndarray,
    frame: np.ndarray,
    clip_x: int,
    clip_y: int,
    clip_w: int,
    clip_h: int,
    source_size: VideoSize,
    transform: Transform,
) -> None:
    """Mirror of the canvas drawVideoCoverWithTransform logic."""
    zoom = max(0.1, float(transform.zoom))
    cover_scale = max(clip_w / source_size.width, clip_h / source_size.height)
    draw_w = source_size.width * cover_scale
    draw_h = source_size.height * cover_scale

    max_offset_x = max(0.0, ((draw_w * zoom) - clip_w) / 2)
    max_offset_y = max(0.0, ((draw_h * zoom) - clip_h) / 2)
    pos_x = clamp(float(transform.pos_x), -max_offset_x, max_offset_x)
    pos_y = clamp(float(transform.pos_y), -max_offset_y, max_offset_y)

    target_w = max(1, int(round(draw_w * zoom)))
    target_h = max(1, int(round(draw_h * zoom)))
    resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

    left = int(round(clip_x + (clip_w / 2) + pos_x - (target_w / 2)))
    top = int(round(clip_y + (clip_h / 2) + pos_y - (target_h / 2)))

    x1 = max(left, clip_x)
    y1 = max(top, clip_y)
    x2 = min(left + target_w, clip_x + clip_w)
    y2 = min(top + target_h, clip_y + clip_h)

    if x2 <= x1 or y2 <= y1:
        return

    sx1 = x1 - left
    sy1 = y1 - top
    sx2 = sx1 + (x2 - x1)
    sy2 = sy1 + (y2 - y1)

    canvas[y1:y2, x1:x2] = resized[sy1:sy2, sx1:sx2]


def build_preview_reference(specs: list[SegmentSpec], input_props: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "preview_reference.mp4"

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, FPS, (COMPOSITION_WIDTH, COMPOSITION_HEIGHT))
    if not writer.isOpened():
        raise RuntimeError("Failed to open preview reference writer")

    segments_props = input_props.get("segments", [])

    for spec in specs:
        seg_props = segments_props[spec.index]
        split_ratio = float(seg_props.get("splitRatio", 0.5))
        transforms = seg_props.get("visualTransforms", {})
        aroll_t = transforms.get("aroll", {})
        broll_t = transforms.get("broll", {})

        duration_frames = max(1, int(round(spec.duration_sec * FPS)))

        aroll_frames = read_video_frames(PUBLIC_DIR / spec.aroll_src, duration_frames)
        broll_frames = (
            read_video_frames(PUBLIC_DIR / spec.broll_src, duration_frames)
            if spec.layout == "half_and_half" and spec.broll_src
            else None
        )

        safe_split = clamp(split_ratio, 0.0, 1.0)
        top_h = int(math.floor(COMPOSITION_HEIGHT * safe_split))
        bottom_h = COMPOSITION_HEIGHT - top_h

        for i in range(duration_frames):
            canvas = np.zeros((COMPOSITION_HEIGHT, COMPOSITION_WIDTH, 3), dtype=np.uint8)

            if spec.layout == "half_and_half" and broll_frames is not None and spec.broll_size is not None:
                blit_cover_with_transform(
                    canvas,
                    broll_frames[i],
                    0, 0, COMPOSITION_WIDTH, max(1, top_h),
                    spec.broll_size,
                    Transform(
                        zoom=float(broll_t.get("zoom", 1.0)),
                        pos_x=float(broll_t.get("posX", 0.0)),
                        pos_y=float(broll_t.get("posY", 0.0)),
                    ),
                )
                blit_cover_with_transform(
                    canvas,
                    aroll_frames[i],
                    0, top_h, COMPOSITION_WIDTH, max(1, bottom_h),
                    spec.aroll_size,
                    Transform(
                        zoom=float(aroll_t.get("zoom", 1.0)),
                        pos_x=float(aroll_t.get("posX", 0.0)),
                        pos_y=float(aroll_t.get("posY", 0.0)),
                    ),
                )
            else:
                blit_cover_with_transform(
                    canvas,
                    aroll_frames[i],
                    0, 0, COMPOSITION_WIDTH, COMPOSITION_HEIGHT,
                    spec.aroll_size,
                    Transform(
                        zoom=float(aroll_t.get("zoom", 1.0)),
                        pos_x=float(aroll_t.get("posX", 0.0)),
                        pos_y=float(aroll_t.get("posY", 0.0)),
                    ),
                )

            writer.write(canvas)

    writer.release()
    return out_path


def _region_mae(diff: np.ndarray) -> dict:
    """Split frame into left / center / right thirds and return MAE per region."""
    w = diff.shape[1]
    third = w // 3
    return {
        "left":   float(np.mean(diff[:, :third])),
        "center": float(np.mean(diff[:, third : 2 * third])),
        "right":  float(np.mean(diff[:, 2 * third :])),
    }


def _estimate_shift(ref: np.ndarray, other: np.ndarray, max_shift: int = 80) -> tuple[int, int]:
    """Estimate (dx, dy) pixel shift of `other` relative to `ref` via cross-correlation.

    Returns the (x, y) shift that minimises the difference, clamped to ±max_shift px.
    Positive dx means `other` is shifted to the right relative to `ref`.
    """
    # Work in grayscale and at half resolution for speed
    gray_ref   = cv2.cvtColor(cv2.resize(ref,   (540, 960)), cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray_other = cv2.cvtColor(cv2.resize(other, (540, 960)), cv2.COLOR_BGR2GRAY).astype(np.float32)

    result = cv2.matchTemplate(gray_ref, gray_other, cv2.TM_CCOEFF_NORMED)
    _, _, _, max_loc = cv2.minMaxLoc(result)
    # max_loc is the top-left corner of the best match in `ref`
    # shift = max_loc - (0, 0) in the half-res grid
    dx = max_loc[0] * 2  # scale back to full res
    dy = max_loc[1] * 2
    # Clamp
    dx = max(-max_shift, min(max_shift, dx))
    dy = max(-max_shift, min(max_shift, dy))
    return int(dx), int(dy)


def _save_side_by_side(
    ref_frame: np.ndarray,
    rem_frame: np.ndarray,
    diff_frame: np.ndarray,
    out_path: Path,
    label: str,
) -> None:
    """Save a horizontally stacked reference | remotion | diff image."""
    h = COMPOSITION_HEIGHT // 4  # quarter-size for manageable file size
    w = COMPOSITION_WIDTH  // 4
    ref_small  = cv2.resize(ref_frame,  (w, h))
    rem_small  = cv2.resize(rem_frame,  (w, h))
    diff_small = cv2.resize(diff_frame, (w, h))

    # Amplify diff for visibility
    diff_vis = cv2.convertScaleAbs(diff_small, alpha=4.0)

    # Add labels
    font = cv2.FONT_HERSHEY_SIMPLEX
    for img, text in [(ref_small, "PREVIEW REF"), (rem_small, "REMOTION"), (diff_vis, "DIFF x4")]:
        cv2.putText(img, text, (4, 18), font, 0.5, (0, 255, 255), 1, cv2.LINE_AA)

    combined = np.hstack([ref_small, rem_small, diff_vis])
    cv2.putText(combined, label, (4, h - 6), font, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(out_path), combined)


def compare_videos(
    reference_path: Path,
    remotion_path: Path,
    specs: list[SegmentSpec],
    save_frames: bool = False,
) -> dict:
    cap_ref = cv2.VideoCapture(str(reference_path))
    cap_rem = cv2.VideoCapture(str(remotion_path))

    if not cap_ref.isOpened() or not cap_rem.isOpened():
        raise RuntimeError("Failed to open one of the videos for comparison")

    frames_dir = OUT_DIR / "frames"
    if save_frames:
        frames_dir.mkdir(parents=True, exist_ok=True)

    frame_idx = 0
    per_frame_mae: list[float] = []

    segment_ranges: list[tuple[int, int, int]] = []
    cursor = 0
    for spec in specs:
        seg_frames = max(1, int(round(spec.duration_sec * FPS)))
        segment_ranges.append((spec.index, cursor, cursor + seg_frames))
        cursor += seg_frames

    # Keep per-segment per-frame data for spatial analysis
    seg_frame_data: dict[int, list[dict]] = {spec.index: [] for spec in specs}

    while True:
        ok_ref, frame_ref = cap_ref.read()
        ok_rem, frame_rem = cap_rem.read()

        if not ok_ref and not ok_rem:
            break
        if ok_ref != ok_rem:
            raise RuntimeError("Video lengths differ during comparison")

        diff = cv2.absdiff(frame_ref, frame_rem)
        mae = float(np.mean(diff))
        per_frame_mae.append(mae)

        # Determine which segment this frame belongs to
        seg_index = -1
        for sidx, start, end in segment_ranges:
            if start <= frame_idx < end:
                seg_index = sidx
                break

        if seg_index >= 0:
            regions = _region_mae(diff)
            seg_frame_data[seg_index].append({"frame": frame_idx, "mae": mae, "regions": regions})

        frame_idx += 1

    cap_ref.release()
    cap_rem.release()

    max_idx = int(np.argmax(per_frame_mae)) if per_frame_mae else -1

    # Per-segment summary with spatial analysis
    by_segment: list[dict] = []
    for seg_index, start, end in segment_ranges:
        seg_values = per_frame_mae[start:end]
        frames_data = seg_frame_data.get(seg_index, [])

        # Aggregate region MAE
        if frames_data:
            left_maes   = [f["regions"]["left"]   for f in frames_data]
            center_maes = [f["regions"]["center"] for f in frames_data]
            right_maes  = [f["regions"]["right"]  for f in frames_data]
            spatial = {
                "mean_mae_left":   float(np.mean(left_maes)),
                "mean_mae_center": float(np.mean(center_maes)),
                "mean_mae_right":  float(np.mean(right_maes)),
            }
            # Detect directional bias
            lr_diff = spatial["mean_mae_left"] - spatial["mean_mae_right"]
            if abs(lr_diff) > 3:
                spatial["horizontal_bias"] = "left_worse" if lr_diff > 0 else "right_worse"
            else:
                spatial["horizontal_bias"] = "none"
        else:
            spatial = {}

        seg_summary = {
            "segment_index": seg_index,
            "frame_start": start,
            "frame_end_exclusive": end,
            "mean_mae": float(np.mean(seg_values)) if seg_values else 0.0,
            "p95_mae":  float(np.percentile(seg_values, 95)) if seg_values else 0.0,
            "max_mae":  float(np.max(seg_values)) if seg_values else 0.0,
            "spatial":  spatial,
        }

        # Estimate pixel shift on the frame with highest MAE for this segment
        if seg_values and save_frames:
            worst_local = int(np.argmax(seg_values))
            worst_global = start + worst_local
            # Re-read that specific frame
            cap_ref2 = cv2.VideoCapture(str(reference_path))
            cap_rem2 = cv2.VideoCapture(str(remotion_path))
            for _ in range(worst_global + 1):
                ok_r, worst_ref = cap_ref2.read()
                ok_m, worst_rem = cap_rem2.read()
            cap_ref2.release()
            cap_rem2.release()

            if ok_r and ok_m:
                dx, dy = _estimate_shift(worst_ref, worst_rem)
                seg_summary["estimated_shift_px"] = {"dx": dx, "dy": dy}

                diff_vis = cv2.absdiff(worst_ref, worst_rem)
                out_path = frames_dir / f"seg{seg_index:02d}_worst_frame{worst_global:04d}.png"
                _save_side_by_side(
                    worst_ref, worst_rem, diff_vis, out_path,
                    f"seg{seg_index} frame{worst_global} mae={seg_values[worst_local]:.1f} shift=({dx},{dy})"
                )
                print(f"  Saved: {out_path.relative_to(ROOT)}")

            # Also save frame 0 of this segment
            cap_ref3 = cv2.VideoCapture(str(reference_path))
            cap_rem3 = cv2.VideoCapture(str(remotion_path))
            for _ in range(start + 1):
                ok_r0, f0_ref = cap_ref3.read()
                ok_m0, f0_rem = cap_rem3.read()
            cap_ref3.release()
            cap_rem3.release()
            if ok_r0 and ok_m0:
                diff0 = cv2.absdiff(f0_ref, f0_rem)
                out_path0 = frames_dir / f"seg{seg_index:02d}_frame0.png"
                _save_side_by_side(
                    f0_ref, f0_rem, diff0, out_path0,
                    f"seg{seg_index} frame0 mae={float(np.mean(diff0)):.1f}"
                )
                print(f"  Saved: {out_path0.relative_to(ROOT)}")

        by_segment.append(seg_summary)

    return {
        "frames_compared": frame_idx,
        "mean_mae":   float(np.mean(per_frame_mae)) if per_frame_mae else 0.0,
        "p95_mae":    float(np.percentile(per_frame_mae, 95)) if per_frame_mae else 0.0,
        "max_mae":    float(np.max(per_frame_mae)) if per_frame_mae else 0.0,
        "max_mae_frame": max_idx,
        "by_segment": by_segment,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--save-frames", action="store_true",
        help="Save PNG side-by-side comparison frames into out/frames/",
    )
    parser.add_argument(
        "--remotion-output", default=str(OUT_DIR / "remotion_after_fix.mp4"),
        help="Path to the Remotion-rendered mp4",
    )
    args = parser.parse_args()

    remotion_output = Path(args.remotion_output)
    if not remotion_output.is_file():
        print(
            f"ERROR: Remotion output not found: {remotion_output}\n"
            f"Render first:  cd remotion-src && npx remotion render MyVideo ../out/remotion_after_fix.mp4",
            file=sys.stderr,
        )
        sys.exit(1)

    specs = load_specs()
    input_props = json.loads((SRC_DIR / "inputProps.json").read_text("utf-8"))

    print("Building preview reference…")
    ref_path = build_preview_reference(specs, input_props)
    print(f"Preview reference: {ref_path.relative_to(ROOT)}")
    print(f"Remotion output:   {remotion_output.relative_to(ROOT)}")

    if args.save_frames:
        print(f"Saving comparison frames to out/frames/…")

    stats = compare_videos(ref_path, remotion_output, specs, save_frames=args.save_frames)

    print(json.dumps(stats, indent=2))

    # Print a human-readable spatial summary
    print("\n── Spatial MAE summary (left / center / right thirds) ──")
    for seg in stats["by_segment"]:
        spatial = seg.get("spatial", {})
        if spatial:
            bias = spatial.get("horizontal_bias", "?")
            print(
                f"  Seg {seg['segment_index']}: "
                f"left={spatial.get('mean_mae_left', 0):.1f}  "
                f"center={spatial.get('mean_mae_center', 0):.1f}  "
                f"right={spatial.get('mean_mae_right', 0):.1f}  "
                f"bias={bias}"
            )
            if bias != "none":
                print(f"    ⚠  Directional difference detected ({bias}) — possible horizontal shift")
        shift = seg.get("estimated_shift_px")
        if shift:
            print(f"    Estimated shift on worst frame: dx={shift['dx']}px, dy={shift['dy']}px")


if __name__ == "__main__":
    main()
