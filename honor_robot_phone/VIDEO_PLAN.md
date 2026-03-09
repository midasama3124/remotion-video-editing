# Honor Robot Phone — Video Plan

> Project-specific edit plan based on `reference.mov` analysis.
> For reusable guidelines, see `docs/` folder.

## Reference Analysis

| Property       | Value                                |
| -------------- | ------------------------------------ |
| File           | `video/reference.mov`                |
| Resolution     | 1080×1920 (9:16 vertical)           |
| Duration       | 50.4 seconds                         |
| FPS            | 30                                   |
| Total frames   | ~1512                                |
| Scene changes  | ~24 (avg cut every ~2.1s)           |

## Source Footage Inventory

### A-Roll

| File       | Resolution  | Duration | FPS    | Format | Notes                          |
| ---------- | ----------- | -------- | ------ | ------ | ------------------------------ |
| aroll.mp4  | 3840×2160   | 621.7s   | ~30    | H.264  | Landscape, needs crop for 9:16 |

### B-Roll

| File        | Resolution  | Duration | FPS | Orientation | Format |
| ----------- | ----------- | -------- | --- | ----------- | ------ |
| broll1.mp4  | 720×1280    | 36.7s    | 30  | Portrait    | H.264  |
| broll2.webm | 2160×3840   | 51.4s    | ~30 | Portrait    | VP9    |
| broll3.webm | 3840×2160   | 144.8s   | ~24 | Landscape   | VP9    |
| broll4.mp4  | 1920×1080   | 387.5s   | ~60 | Landscape   | H.264  |
| broll5.mp4  | 1920×1080   | 134.0s   | 25  | Landscape   | H.264  |
| broll6.mp4  | 1920×1080   | 165.2s   | 30  | Landscape   | H.264  |
| broll7.mp4  | 2560×1440   | 474.0s   | 60  | Landscape   | VP9    |
| broll8.mp4  | 1920×1080   | 172.2s   | ~24 | Landscape   | H.264  |

**Note**: Most B-Roll is landscape and requires the dark background + centered placement treatment (see `docs/04_BROLL.md`). `broll1` and `broll2` are portrait and can fill the canvas directly.

## Timeline Breakdown (from Reference)

Based on scene change analysis of `reference.mov`:

### Phase 1: Hook (0s - 1.2s)

```
SEGMENT 1:
  Time:       0.0s - 1.2s (1.2s, 36 frames)
  Visual:     A-Roll Full-Frame
  A-Roll:     aroll.mp4 @ TBD (identify hook statement)
  Transition: None (opening)
  SFX:        Cinematic Boom.mp3 @ 0s (volume: 0.6)
  Text:       Hook text overlay (top safe zone area)
```

### Phase 2: Context / Product Reveal (1.2s - 10.4s)

```
SEGMENT 2:
  Time:       1.2s - 2.8s (1.6s, 47 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut from Hook

SEGMENT 3:
  Time:       2.8s - 4.6s (1.8s, 54 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 4:
  Time:       4.6s - 7.6s (3.0s, 90 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 5:
  Time:       7.6s - 10.4s (2.8s, 83 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut
```

### Phase 3: Core Content (10.4s - 35.3s)

```
SEGMENT 6:
  Time:       10.4s - 13.1s (2.7s, 81 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 7:
  Time:       13.1s - 16.1s (3.0s, 89 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 8:
  Time:       16.1s - 17.0s (0.9s, 28 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 9:
  Time:       17.0s - 17.8s (0.8s, 23 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut (quick cuts — building energy)

SEGMENT 10:
  Time:       17.8s - 19.4s (1.6s, 49 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 11:
  Time:       19.4s - 20.0s (0.6s, 19 frames)
  Visual:     B-Roll (deep dark transition)
  B-Roll:     TBD @ TBD
  Transition: Dark Flash

SEGMENT 12:
  Time:       20.0s - 21.0s (1.0s, 30 frames)
  Visual:     A-Roll Full-Frame (emphasis)
  A-Roll:     aroll.mp4 @ TBD
  Transition: Hard Cut
  SFX:        modern_select.mp3 @ 20.0s (volume: 0.5)

SEGMENT 13:
  Time:       21.0s - 23.0s (2.0s, 60 frames)
  Visual:     A-Roll Full-Frame (continued)
  A-Roll:     aroll.mp4 @ TBD
  Transition: Hard Cut

SEGMENT 14:
  Time:       23.0s - 25.9s (2.8s, 85 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 15:
  Time:       25.9s - 27.4s (1.5s, 46 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 16:
  Time:       27.4s - 31.8s (4.4s, 133 frames)
  Visual:     A-Roll Full-Frame (extended on-camera segment)
  A-Roll:     aroll.mp4 @ TBD
  Transition: Hard Cut
  SFX:        bass_sharp_detail_riser.mp3 @ 27.4s (volume: 0.5)

SEGMENT 17:
  Time:       31.8s - 33.9s (2.1s, 63 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 18:
  Time:       33.9s - 35.3s (1.4s, 43 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut
```

### Phase 4: Climax / Dark Transition (35.3s - 42.4s)

```
SEGMENT 19:
  Time:       35.3s - 37.8s (2.4s, 73 frames)
  Visual:     Dark transition → B-Roll
  B-Roll:     TBD (dark/moody clip)
  Transition: Fade to Black
  SFX:        riser_effects.mp3 @ 35.3s (volume: 0.5)

SEGMENT 20:
  Time:       37.8s - 39.3s (1.5s, 45 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 21:
  Time:       39.3s - 40.9s (1.6s, 49 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 22:
  Time:       40.9s - 42.4s (1.4s, 43 frames)
  Visual:     B-Roll (letterbox, dark)
  B-Roll:     TBD @ TBD
  Transition: Dark Flash
```

### Phase 5: Closing (42.4s - 50.4s)

```
SEGMENT 23:
  Time:       42.4s - 43.3s (0.9s, 28 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 24:
  Time:       43.3s - 45.7s (2.3s, 70 frames)
  Visual:     B-Roll (letterbox)
  B-Roll:     TBD @ TBD
  Transition: Hard Cut

SEGMENT 25:
  Time:       45.7s - 50.4s (4.7s, 141 frames)
  Visual:     B-Roll montage + closing
  B-Roll:     TBD @ TBD (hero shots)
  Transition: Hard Cut → Fade to Black
  SFX:        Cinematic Boom.mp3 @ 45.7s (volume: 0.5)
  Text:       CTA overlay (bottom safe zone)
```

## A-Roll Audio Mapping

The A-Roll audio runs continuously as narration. Key trim points from `aroll.mp4` need to be identified by:

1. Listening to the raw A-Roll and noting speech segments
2. Matching speech content to what plays in `reference.mov`
3. The A-Roll audio track should be trimmed to match the final ~50.4s duration

**TODO**: Run speech/silence detection on `aroll.mp4` to identify usable segments:

```bash
ffmpeg -i video/aroll.mp4 -af silencedetect=noise=-30dB:d=0.5 -f null - 2>&1 | grep silence
```

## B-Roll Assignment

Map each B-Roll source to the segments where it's used. This requires visual matching against the reference:

| B-Roll File  | Likely Content                    | Suggested Segments |
| ------------ | --------------------------------- | ------------------ |
| broll1.mp4   | Portrait product shot             | 2-3 (reveal)       |
| broll2.webm  | Portrait close-up                 | 4-5                |
| broll3.webm  | Landscape product demo            | 6-8                |
| broll4.mp4   | Feature demonstration             | 9-11, 14-15        |
| broll5.mp4   | Secondary features                | 17-18              |
| broll6.mp4   | UI/software demo                  | 20-21              |
| broll7.mp4   | Detailed feature showcase         | 23-24              |
| broll8.mp4   | Hero/closing shots                | 25                 |

**Note**: These assignments are preliminary estimates. Final mapping requires visual comparison with the reference.

## Music Selection

Recommended: **GLORY - Ogryzek.mp3** — the cinematic, epic mood matches a tech product showcase.

- Volume: 0.2 (20%)
- Fade in: 0-0.5s
- Fade out: 48.4s-50.4s

## Composition Configuration

```tsx
<Composition
  id="HonorRobotPhone"
  component={HonorRobotPhone}
  width={1080}
  height={1920}
  fps={30}
  durationInFrames={1512}   // 50.4s × 30fps
/>
```
