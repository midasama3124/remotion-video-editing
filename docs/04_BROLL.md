# B-Roll Guidelines

B-Roll is supplementary footage that visually supports the narration. It shows the product, demonstrates features, and keeps the visual pace engaging.

## Source Handling

- B-Roll files start with the prefix `broll` followed by a number (e.g., `broll1.mp4`, `broll2.webm`)
- B-Roll can arrive in **any resolution or aspect ratio** — landscape, portrait, or square
- B-Roll clips are numbered sequentially but do **not** need to be used in order
- Not all B-Roll clips need to be used — select based on relevance to the narration

### Common Resolutions Encountered

| Aspect     | Example               | Handling                          |
| ---------- | --------------------- | --------------------------------- |
| 16:9       | 1920×1080, 3840×2160  | Center in frame with dark bg fill |
| 9:16       | 2160×3840, 1080×1920  | Scale to fill canvas directly     |
| Other      | 2560×1440, etc.       | Center and pad with dark bg       |

## Formatting for Vertical Canvas

### Landscape B-Roll (most common)

Landscape clips don't fill the 9:16 canvas. Two strategies:

#### Strategy A: Centered with Dark Background (Default)

Place the B-Roll centered vertically with `dark_bg1.mp4` filling the remaining space.

```tsx
{/* Background layer */}
<OffthreadVideo
  src={staticFile("../assets/dark_bg1.mp4")}
  style={{ width: 1080, height: 1920, objectFit: "cover" }}
  loop
/>

{/* B-Roll centered */}
<OffthreadVideo
  src={staticFile("video/broll1.mp4")}
  startFrom={trimStartFrame}
  style={{
    width: 1080,
    height: "auto",      // Maintain aspect ratio
    position: "absolute",
    top: "50%",
    transform: "translateY(-50%)",
  }}
/>
```

This creates the **letterbox effect** seen in the reference video (dark areas top and bottom).

#### Strategy B: Scale to Fill (Zoom)

For clips where the subject is centered, scale up to fill the vertical frame:

```tsx
<OffthreadVideo
  src={staticFile("video/broll1.mp4")}
  startFrom={trimStartFrame}
  style={{
    width: "auto",
    height: 1920,
    position: "absolute",
    left: "50%",
    transform: "translateX(-50%)",
    objectFit: "cover",
  }}
/>
```

Use sparingly — only when the subject fills the center of frame and cropping sides is acceptable.

### Portrait B-Roll

Portrait clips that are already 9:16 can fill the canvas directly:

```tsx
<OffthreadVideo
  src={staticFile("video/broll2.webm")}
  startFrom={trimStartFrame}
  style={{ width: 1080, height: 1920, objectFit: "cover" }}
/>
```

## Trimming & Timing

### Clip Selection

1. Review each B-Roll clip and note its content/subject
2. Map narration segments from A-Roll to relevant B-Roll clips
3. Select the best portion of each clip (products, features, close-ups)

### Cut Duration Guidelines

Based on the reference video analysis (~50s video with ~24 scene changes):

| Cut Type          | Duration       | Frames (30fps) | Usage                      |
| ----------------- | -------------- | -------------- | -------------------------- |
| Quick cut         | 0.5-1.5s       | 15-45          | Montage, rapid showcase    |
| Standard cut      | 1.5-3s         | 45-90          | Feature demonstration      |
| Lingering cut     | 3-5s           | 90-150         | Hero shot, dramatic moment |

### Pacing Pattern (from reference)

The reference video follows this rhythm:

- **Sec 0-1**: Full-frame hook (A-Roll)
- **Sec 1-21**: Rapid B-Roll cuts (1-3s each) with A-Roll voiceover
- **Sec 21-23**: Full-frame A-Roll emphasis
- **Sec 23-27**: B-Roll cuts
- **Sec 27-32**: Full-frame A-Roll segment
- **Sec 32-35**: B-Roll
- **Sec 35-38**: Dark transition
- **Sec 38-50**: B-Roll montage with varied pacing to close

Average cut length: **~2 seconds** — keeps engagement high for Reels format.

## B-Roll Enhancement

### Slow Motion

For dramatic/hero shots, slow down the playback:

```tsx
<OffthreadVideo
  src={staticFile("video/broll3.webm")}
  startFrom={trimStartFrame}
  playbackRate={0.5}  // Half speed
  style={{ /* ... */ }}
/>
```

### Ken Burns Effect (Subtle Pan/Zoom)

Add motion to static-feeling clips:

```tsx
const frame = useCurrentFrame();
const scale = interpolate(frame, [0, durationInFrames], [1, 1.1]);
const translateX = interpolate(frame, [0, durationInFrames], [0, -20]);

<div style={{ transform: `scale(${scale}) translateX(${translateX}px)` }}>
  <OffthreadVideo src={staticFile("video/broll4.mp4")} /* ... */ />
</div>
```

## Audio Handling

- **Strip B-Roll audio by default** — A-Roll narration is the primary track
- Exception: If B-Roll contains meaningful sound (product demo audio), mix at low volume
- Use `volume={0}` on B-Roll `<OffthreadVideo>` components unless intentionally mixing

```tsx
<OffthreadVideo
  src={staticFile("video/broll1.mp4")}
  volume={0}          // Mute B-Roll audio
  startFrom={trimStartFrame}
/>
```
