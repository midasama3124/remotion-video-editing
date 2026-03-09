# Video Structure Template

This template defines the standard flow for an Instagram Reels-style tech review video. Adapt durations and sections to match your project's narration.

## Standard Video Anatomy (~30-60 seconds)

```
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 1: HOOK (0-3s)                                                │
│   ├─ Full-frame A-Roll (face, dramatic statement)                   │
│   ├─ Hook text overlay (bold, short, curiosity-driven)              │
│   ├─ SFX: Cinematic Boom or riser on first frame                   │
│   └─ Music fades in                                                │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 2: CONTEXT / SETUP (3-10s)                                    │
│   ├─ B-Roll montage (product reveal, overview shots)                │
│   ├─ A-Roll as bubble OR voiceover only                             │
│   ├─ Quick cuts (1-2s each)                                         │
│   └─ SFX: 1-2 accents on key reveals                               │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 3: CORE CONTENT (10-35s)                                      │
│   ├─ B-Roll demonstrating features, close-ups                       │
│   ├─ A-Roll alternates: bubble mode ↔ full-frame emphasis           │
│   ├─ Standard cuts (1.5-3s each)                                    │
│   ├─ SFX: Sparse accents on transitions                             │
│   └─ Dark flash transitions between sub-topics                     │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 4: CLIMAX / KEY MOMENT (35-45s)                               │
│   ├─ Fastest cuts (0.5-1.5s each)                                   │
│   ├─ Full-frame A-Roll for maximum impact statement                 │
│   ├─ SFX: Build (riser) → Impact (boom)                            │
│   └─ Optional dark transition before/after                          │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 5: CLOSING (45-50s)                                           │
│   ├─ B-Roll hero shot or A-Roll sign-off                            │
│   ├─ CTA text overlay (follow, comment, share)                      │
│   ├─ Music fades out                                                │
│   └─ Optional end card                                              │
└─────────────────────────────────────────────────────────────────────┘
```

## Composition Structure (Remotion)

```tsx
const MainVideo: React.FC = () => {
  const { fps, durationInFrames } = useVideoConfig();

  return (
    <AbsoluteFill>
      {/* Layer 0: Dark Background (always present, looped) */}
      <DarkBackground />

      {/* Layer 1: B-Roll Track */}
      <BRollTrack />

      {/* Layer 2: A-Roll Track (switches between full-frame and bubble) */}
      <ARollTrack />

      {/* Layer 3: Text Overlays */}
      <TextOverlays />

      {/* Layer 4: Audio Mix */}
      <AudioMix />
    </AbsoluteFill>
  );
};
```

### Component Breakdown

Each component maps to one concern:

| Component         | Responsibility                                       | Doc Reference           |
| ----------------- | ---------------------------------------------------- | ----------------------- |
| `DarkBackground`  | Looped `dark_bg1.mp4` filling the canvas             | `02_CANVAS_LAYOUT.md`   |
| `BRollTrack`      | Sequenced B-Roll clips, trimmed and positioned       | `04_BROLL.md`           |
| `ARollTrack`      | A-Roll in full-frame or bubble mode per section       | `03_AROLL.md`           |
| `TextOverlays`    | Hook text, captions, CTA                              | `02_CANVAS_LAYOUT.md`   |
| `AudioMix`        | Narration + music + SFX layered                       | `06_AUDIO.md`           |

## Phase Timing Worksheet

Fill this in for each project:

| Phase          | Start (s) | End (s) | Duration (s) | A-Roll Mode     | B-Roll Clips Used | SFX Used          |
| -------------- | --------- | ------- | ------------- | --------------- | ------------------ | ----------------- |
| Hook           |           |         |               | Full-frame      |                    |                   |
| Context/Setup  |           |         |               | Bubble/VO       |                    |                   |
| Core Content   |           |         |               | Mixed           |                    |                   |
| Climax         |           |         |               | Full-frame      |                    |                   |
| Closing        |           |         |               | Full/Bubble     |                    |                   |

## Edit Decision List (EDL) Format

For each segment in the final video, define:

```
SEGMENT <N>:
  Time:       <start_time>s - <end_time>s (<duration>s, <frames> frames)
  Visual:     <A-Roll Full | A-Roll Bubble | B-Roll Only>
  B-Roll:     <broll_file> @ <source_start>s-<source_end>s
  A-Roll:     <aroll_file> @ <source_start>s-<source_end>s
  Transition: <Hard Cut | Dark Flash | Fade | Scale>
  SFX:        <sfx_file> @ <trigger_time>s (volume: <0-1>)
  Text:       "<overlay text>" (position: <top|center|bottom>)
```

## Rendering Checklist

Before final render:

- [ ] All clips trimmed to correct in/out points
- [ ] A-Roll audio is clear and narration synced
- [ ] B-Roll audio is muted (unless intentional)
- [ ] Safe zone compliance verified with overlay
- [ ] Transitions are smooth and on-beat
- [ ] SFX are well-timed and not overused
- [ ] Music fades in/out properly
- [ ] Total duration matches target (30-60s for Reels)
- [ ] No black frames unintentionally present
- [ ] Bubble A-Roll is visible and within safe zone
