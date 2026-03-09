# A-Roll Guidelines

A-Roll is the primary narrator/speaker footage. It anchors the viewer's attention and drives the narrative.

## Source Handling

- A-Roll files start with the prefix `aroll` inside each project's `video/` folder
- A-Roll is typically recorded in landscape (e.g., 3840×2160) and must be reformatted for 9:16
- Audio from the A-Roll is the **primary audio track** — it carries the narration/voiceover

### Trimming

The raw A-Roll is usually much longer than the final video. Trim points should be determined by:

1. Listening to the A-Roll audio and noting narration segments
2. Matching narration segments to the reference video's timing
3. Using FFmpeg to extract precise timestamps (see Remotion skill `rules/ffmpeg.md`)

## Display Modes

### Mode 1: Standalone (Full-Frame)

The A-Roll fills the entire 1080×1920 canvas. Used for:

- **Hook / attention grab** — first 1-3 seconds to capture the viewer
- **Key emphasis points** — reaction shots, dramatic statements
- **Closing** — final call-to-action or sign-off

#### Formatting

Since A-Roll is typically landscape, apply a **crop and scale** to fill the vertical frame:

```tsx
<OffthreadVideo
  src={staticFile("video/aroll.mp4")}
  startFrom={trimStartFrame}
  style={{
    width: "auto",
    height: "100%",        // Fill vertical frame
    position: "absolute",
    left: "50%",
    transform: "translateX(-50%)",  // Center crop
  }}
/>
```

Alternatively, **scale to width** and crop top/bottom if the subject is centered:

```tsx
style={{
  width: "100%",
  height: "auto",
  position: "absolute",
  top: "50%",
  transform: "translateY(-50%)",
}}
```

### Mode 2: Bubble (Picture-in-Picture)

The A-Roll appears as a small circular overlay in the bottom-left corner while B-Roll plays in the main frame. Used for:

- **Continuous narration** over B-Roll footage
- **Commentary while showing product** — viewer sees the product and the speaker simultaneously

#### Positioning & Sizing

| Property     | Value             | Notes                                     |
| ------------ | ----------------- | ----------------------------------------- |
| Shape        | Circle            | Use `borderRadius: "50%"`                 |
| Diameter     | 200-250px         | Large enough to see face clearly          |
| Position X   | 80px from left    | Within Instagram safe zone side margin    |
| Position Y   | ~1350-1500px      | Above bottom unsafe zone (~350px margin)  |
| Border       | 3px solid white   | Ensures visibility against dark backgrounds|
| Shadow       | Subtle drop shadow| `boxShadow: "0 4px 12px rgba(0,0,0,0.4)"`|

#### Implementation

```tsx
<div
  style={{
    position: "absolute",
    bottom: 420,         // Above Instagram bottom UI
    left: 80,            // Within side safe zone
    width: 220,
    height: 220,
    borderRadius: "50%",
    overflow: "hidden",
    border: "3px solid white",
    boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
    zIndex: 10,
  }}
>
  <OffthreadVideo
    src={staticFile("video/aroll.mp4")}
    startFrom={trimStartFrame}
    style={{
      width: "auto",
      height: "100%",
      position: "absolute",
      left: "50%",
      transform: "translateX(-50%)",
    }}
  />
</div>
```

#### Visibility Safeguards

- Bubble must remain **within the Instagram safe zone** at all times
- Test against `instagram_safe_zone.png` overlay to verify placement
- On very dark B-Roll, the white border provides sufficient contrast
- On very bright B-Roll, the drop shadow ensures the bubble pops

## Transitions Between Modes

When switching from Bubble to Standalone (or vice versa):

- Use a **scale + position animation** over 6-10 frames (0.2-0.33s)
- The bubble can "grow" into full-frame and "shrink" back
- Alternatively, use a **quick cut** matching the rhythm of the edit

## Audio Handling

- A-Roll audio is **always present** regardless of display mode
- When in bubble mode, A-Roll audio continues as voiceover
- Volume should remain consistent across mode switches
- If background music is present, A-Roll audio takes priority (see `06_AUDIO.md`)
