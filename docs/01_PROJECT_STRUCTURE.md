# Project Structure & Conventions

## Workspace Layout

```
remotion_videos/
├── assets/                    # Shared assets across all projects
│   ├── dark_bg1.mp4           # Dark animated background (432×768, 30fps, 30s loop)
│   ├── instagram_safe_zone.png # Safe zone overlay reference (1300×2311)
│   ├── sound_effects/         # Shared SFX library
│   │   ├── Cinematic Boom.mp3
│   │   ├── bass_sharp_detail_riser.mp3
│   │   ├── digital_camera_shutter.mp3
│   │   ├── jaws.mp3
│   │   ├── modern_select.mp3
│   │   ├── riser_effects.mp3
│   │   └── short_select.mp3
│   └── soundtrack/            # Background music tracks
│       ├── GLORY - Ogryzek.mp3
│       └── Life's Journey Begins - idokay.mp3
├── docs/                      # Reusable documentation & templates
├── <project_name>/            # One folder per video project
│   └── video/                 # Raw footage for this project
│       ├── aroll.mp4          # A-Roll footage (speaker/narrator)
│       ├── broll1.mp4         # B-Roll clip 1
│       ├── broll2.webm        # B-Roll clip 2
│       └── reference.mov      # Reference edit (the target to replicate)
└── src/                       # Remotion source code (when initialized)
```

## File Naming Conventions

### Per-Project `video/` Folder

| Prefix      | Description                                        |
| ----------- | -------------------------------------------------- |
| `aroll`     | A-Roll footage — the speaker/narrator on camera    |
| `broll<N>`  | B-Roll clips numbered sequentially (broll1, broll2…)|
| `reference` | The finished reference edit to replicate            |

### Supported Formats

- **Video**: `.mp4` (H.264), `.webm` (VP9), `.mov` (H.264)
- **Audio**: `.mp3`
- **Images**: `.png`, `.jpg`

## Creating a New Project

1. Create a folder at the workspace root: `<project_name>/`
2. Create a `video/` subfolder inside it
3. Place the A-Roll file as `video/aroll.mp4`
4. Place B-Roll files as `video/broll1.mp4`, `video/broll2.mp4`, etc.
5. Place the reference edit as `video/reference.mov` (or `.mp4`)
6. Create a `VIDEO_PLAN.md` using the template in `docs/07_VIDEO_STRUCTURE_TEMPLATE.md`

## Asset Priority

Shared assets in `assets/` should be used as much as possible to maintain visual consistency across projects:

- **Background**: Always use `dark_bg1.mp4` as the fallback background
- **Sound effects**: Pull from `assets/sound_effects/` before sourcing externally
- **Soundtrack**: Use tracks from `assets/soundtrack/` when appropriate
- **Safe zone**: Always validate layouts against `instagram_safe_zone.png`

## Supported Visual Formats

Projects can be edited in either of these visual formats:

1. **Standard format**: B-Roll as the main visual layer, with optional A-Roll bubble/full-frame switches
2. **Split-stack format**: **B-Roll fixed on top** and **A-Roll fixed at bottom** of the final 1080×1920 frame

For split-stack projects, keep this naming and planning convention in the EDL/notes:

- `layoutMode: split-stack`
- `topTrack: broll`
- `bottomTrack: aroll`
