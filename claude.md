# Instagram Reels Video Editing Tool — Project Context

> **Purpose of this file:** This document captures the architecture, features, and design decisions established across planning sessions with Claude. It serves as context for AI-assisted development (Copilot, Claude, etc.) to make informed, consistent decisions without re-explaining the project from scratch.

---

## Overview

This is a personal video editing tool built to automate the production of Instagram Reels. The workflow has two distinct phases:

1. **Trimming UI** — A Python-backed browser UI (`video_trimmer_ui.py` + `trimmer_ui.html`) for trimming A-roll and B-roll video clips and assigning visual formats to each segment. Produces structured JSON files that describe every editorial decision.
2. **Remotion Layer** — A TypeScript/React project powered by [Remotion](https://www.remotion.dev) that consumes the JSON outputs and renders the final composed video. Remotion Studio is used for live visual preview and fine-tuning.

The two layers are complementary: the trimmer handles *editorial* decisions (which clips, when), and Remotion handles *visual rendering* (layout, transitions, captions, audio mix).

---

## Supported Formats

Each segment is assigned a `broll_format` string that determines how A-roll and B-roll are composed:

- **`"Half-And-Half Split"`** — B-roll on top, A-roll on bottom. The split ratio is configurable (default 50/50). This is the primary format in active development.
- **`"Bubble PiP"`** — A-roll as main video with a draggable B-roll bubble overlay. Position and size are customizable. Planned for future implementation after Half-And-Half is stable.

---

## Repository Structure

```
<workspace root>/
├── scripts/
│   └── video_trimmer_ui.py       # Python FastAPI/Flask server; all trimmer endpoints
├── trimmer_ui.html               # Single-file browser UI for trimming and format assignment
├── .trimmer_ui_session_backup.json  # Workspace-level config; stores active project, fps, and format presets
├── <project_folder>/             # One folder per reel project (e.g. sports_production/)
│   ├── aroll_segments.json       # A-roll segment timings
│   ├── broll_main_segments.json  # B-roll segment timings + format + visual transforms
│   └── aroll_transcription.json  # Whisper transcription for caption generation (future)
└── remotion-src/                 # Remotion project subfolder
    ├── src/
    │   ├── Root.tsx              # Registers Remotion compositions
    │   ├── Composition.tsx       # Auto-generated: sequences all segments
    │   ├── Segment0.tsx          # Auto-generated: one file per segment
    │   ├── Segment1.tsx
    │   ├── ...
    │   ├── layouts/
    │   │   └── HalfAndHalf.tsx   # Reusable layout component (hand-authored, never overwritten)
    │   └── inputProps.json       # Runtime props for Studio (splitRatio, etc.)
    └── public/
        └── *.mp4                 # Symlinked or copied video files for Remotion to serve
```

---

## JSON Schema

### `broll_main_segments.json` (per segment entry)

```json
{
  "broll_start": 12.4,
  "broll_end": 18.0,
  "aroll_start": 5.1,
  "aroll_end": 10.7,
  "broll_format": "Half-And-Half Split",
  "aroll": {
    "zoom": 1.2,
    "posX": 0,
    "posY": -40
  },
  "broll": {
    "zoom": 1.0,
    "posX": 0,
    "posY": 0
  }
}
```

Transform value constraints: `zoom` ∈ [0.5, 2.0], `posX`/`posY` ∈ [-600, 600].

### `.trimmer_ui_session_backup.json`

```json
{
  "project": "sports_production",
  "mode": "broll",
  "videoFilename": "broll_main.mp4",
  "fps": 30,
  "presets": {
    "Half-And-Half Split": [
      {
        "name": "Default close-up",
        "aroll": { "zoom": 1.2, "posX": 0, "posY": -40 },
        "broll": { "zoom": 1.0, "posX": 0, "posY": 0 },
        "createdAt": "2025-01-01T00:00:00Z"
      }
    ],
    "Bubble": []
  }
}
```

Presets are stored at the workspace level (not per project) and keyed by `broll_format`. This makes them reusable across all projects.

---

## Trimming UI (`trimmer_ui.html` + `video_trimmer_ui.py`)

### Purpose

A browser-based editor for making all editorial decisions before handing off to Remotion. The user trims clips, assigns formats, and tunes per-segment visual transforms here.

### Key UI Components

**Segment cards** — Each B-roll segment has a card showing its timing, the paired A-roll timing, and the assigned format. Cards are the primary interaction unit.

**Transform panel** (per card, collapsed by default) — Reveals zoom, posX, posY sliders for both the A-roll and B-roll layers within that segment. Shows a visual badge when non-default transforms are applied. Includes:
- Per-slider controls with debounced save + inline "Saved" confirmation
- In-memory undo (no server round-trip)
- Reset actions behind a `⋯` overflow menu to prevent accidental resets

**Multi-select mode** — Toggled at the top of the segment list. Enables checkboxes on each card. When 2+ segments are selected, a floating action bar appears with bulk actions: *Apply transforms from…*, *Apply preset*, *Reset selected*.

**Presets toolbar** — Located near the project-level format selector. Manages saved transform presets for the current `broll_format`. Actions: Save current as preset, Apply preset to all, Apply preset to selected. When saving from a project with mixed transform values across segments, prompts the user to choose a reference segment.

**Transform window (canvas preview)** — Live HTML5 canvas preview that shows how A-roll and B-roll will be composed for the current segment, based on the assigned format and transforms. The canvas rendering logic must stay in sync with what Remotion renders — divergence between them is a known source of bugs.

### Backend API (Python server)

| Endpoint | Purpose |
|---|---|
| `POST /api/segments/visual-transform` | Patch transforms for a single segment |
| `POST /api/segments/visual-transform/bulk` | Patch transforms for multiple segments at once |
| `POST /api/generate-remotion` | Trigger generation of Remotion component files from current JSON state |
| `GET /api/presets?format=<broll_format>` | Return saved presets for a format |
| `POST /api/presets` | Save a new named preset |
| `DELETE /api/presets` | Remove a named preset |

**Important:** `POST /api/generate-remotion` must preserve existing transform values when rewriting `inputProps.json` — it should never wipe user tuning on re-generation.

### Video Dimension Probing

The server probes source video dimensions with `ffprobe` to write `brollSourceSize` / `arollSourceSize` into generated Remotion files. **SAR (sample aspect ratio) correction must be applied** — clips re-encoded with FFmpeg's `-2` height rounding can have SAR ≠ 1:1, causing the browser's `videoEl.videoWidth` to differ from the raw stream value. The corrected width formula: `width = round(width * sar_x / sar_y)`. Without this, the canvas preview and Remotion layout will diverge.

---

## Remotion Layer (`remotion-src/`)

### Architecture

The pipeline is **fully programmatic** — no AI calls in the generation path. The Python `generate_remotion` endpoint reads the project's JSON files and writes TypeScript component files. All timing values are hardcoded as integers/floats in the generated files (not read from JSON at runtime), making the generator idempotent.

**Files the generator owns (may overwrite):**
- `src/Segment*.tsx` — one per segment
- `src/Composition.tsx` — sequences all segments
- `src/inputProps.json` — runtime Studio props

**Files the generator must never touch:**
- `src/layouts/` — hand-authored reusable layout components
- `src/Root.tsx` — Remotion composition registration

### `HalfAndHalf.tsx` Layout Component

The primary layout. Accepts these props:

| Prop | Type | Description |
|---|---|---|
| `brollSrc` | string | Path to B-roll video (via `staticFile()`) |
| `arollSrc` | string | Path to A-roll video (via `staticFile()`) |
| `startBroll` / `endBroll` | number | B-roll trim points in frames |
| `startAroll` / `endAroll` | number | A-roll trim points in frames |
| `splitRatio` | number | Top panel height as fraction of total (default 0.5) |
| `brollTransform` | `{ zoom, posX, posY }` | B-roll layer transforms |
| `arollTransform` | `{ zoom, posX, posY }` | A-roll layer transforms |
| `brollSourceSize` | `{ width, height }` | Probed source dimensions (SAR-corrected) |
| `arollSourceSize` | `{ width, height }` | Probed source dimensions (SAR-corrected) |

**Canvas/viewport:** 1080 × 1920 (portrait, 9:16 for Instagram).

**Video component:** Uses Remotion's `<Video>` component (not `Html5Video`). `Html5Video` does not integrate with Remotion's `delayRender`/`continueRender` pipeline and causes timeout failures during headless rendering. `<Video>` is the correct render-safe component for both Studio preview and CLI rendering.

**Layout computation:** `computeVideoLayout()` calculates cover-scale position and dimensions for each panel, mirroring the canvas preview's `drawVideoCover` logic. Both must use the same algorithm to avoid visual drift between the trimmer preview and the final Remotion output.

### Generated `Segment*.tsx` Pattern

Each segment file exports a single functional component that instantiates the appropriate layout with hardcoded timing and transform values. Example:

```tsx
import { HalfAndHalf } from "../layouts/HalfAndHalf";
import { staticFile } from "remotion";

export const Segment0: React.FC = () => (
  <HalfAndHalf
    brollSrc={staticFile("sports_production_broll_seg000.mp4")}
    arollSrc={staticFile("sports_production_aroll_seg000.mp4")}
    startBroll={372}
    endBroll={540}
    startAroll={153}
    endAroll={321}
    splitRatio={0.5}
    brollTransform={{ zoom: 1.0, posX: 0, posY: 0 }}
    arollTransform={{ zoom: 1.2, posX: 0, posY: -40 }}
    brollSourceSize={{ width: 1080, height: 1920 }}
    arollSourceSize={{ width: 1080, height: 1920 }}
  />
);
```

---

## Planned Features (Not Yet Implemented)

These were discussed and scoped but deferred until the Half-And-Half flow is fully stable:

- **Bubble PiP format** — A-roll main video with draggable B-roll bubble overlay; transform controls (position, zoom) extend naturally from the Half-And-Half model.
- **Soundtrack + SFX** — Remotion `<Audio>` components with volume as a function of time; wired to UI controls.
- **Auto captions** — Whisper transcription data already exists in `aroll_transcription.json`; to be rendered as frame-synced animated captions in Remotion.
- **Transitions** — `@remotion/transitions` between segments.
- **Studio → Trimmer round-trip** — Saving fine-tuned `inputProps.json` values back into `broll_main_segments.json`. Deferred; low priority since the trimmer is the source of truth.
- **Transform controls for non-Half-And-Half formats** — Extend presets and transform panels to Bubble and other formats once Half-And-Half is proven.
- **Keyframed transforms** — Only after static transforms are stable.

---

## Key Architectural Decisions and Rationale

**Why Remotion over FFmpeg for the final render?**
The feature set (live preview, draggable bubble, captions, transitions) requires a real-time preview that updates instantly. FFmpeg would require a full re-render per adjustment. Remotion's `<Player>` renders live in the browser and maps directly to React props.

**Why keep the Python trimmer UI?**
The trimmer handles all editorial decisions (which clip, when, paired with what). It produces the JSON that drives Remotion — the two layers are complementary. The trimmer is not replaced by Remotion; it feeds it.

**Why programmatic generation instead of AI manifests?**
All video material is already in place after trimming. Re-running the generator must be fast and deterministic — no LLM calls, no network dependency. The JSON files contain all the information needed to write the Remotion TSX files directly.

**Why hardcode timing values in generated files?**
Idempotency and simplicity. The generator can be re-run any time without producing drift. Runtime JSON parsing adds complexity and a failure mode with no benefit.

**Source of truth for transforms:** The trimmer (`broll_main_segments.json`) is the canonical source. Remotion `inputProps.json` is a derivative. Regeneration must preserve transforms, never reset them.