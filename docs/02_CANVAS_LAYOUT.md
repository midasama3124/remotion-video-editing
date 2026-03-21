# Canvas & Layout — Instagram Optimization

## Output Specifications

| Property    | Value     |
| ----------- | --------- |
| Width       | 1080 px   |
| Height      | 1920 px   |
| Aspect Ratio| 9:16      |
| FPS         | 30        |
| Format      | MP4 (H.264) |

All compositions target **Instagram Reels** vertical format.

## Instagram Safe Zone

The file `assets/instagram_safe_zone.png` (1300×2311) defines the region where content remains visible across all Instagram UI placements (feed, Reels tab, profile grid). Use it as a development overlay.

### Safe Zone Boundaries (approximate, scaled to 1080×1920)

```
┌──────────────────────┐
│     TOP UNSAFE       │  ~250px from top — Instagram header/username overlay
│ ┌──────────────────┐ │
│ │                  │ │
│ │   SAFE ZONE      │ │  Core content area
│ │   (visible on    │ │
│ │    all surfaces)  │ │
│ │                  │ │
│ ┌──────────────────┐ │
│     BOTTOM UNSAFE    │  ~350px from bottom — Instagram captions/buttons/UI
│ ┌──────────────────┐ │
│ │ SIDE MARGINS     │ │  ~60px from each side
└──────────────────────┘
```

### Key Rules

- **No critical text or faces** in the top ~250px or bottom ~350px
- **Side margins**: Keep at least ~60px from each edge
- **A-Roll bubble** must sit within the safe zone (see `03_AROLL.md`)
- **Captions/subtitles** should be positioned in the lower-center safe area (~y: 1300-1550px)
- **Hook text** should be positioned in the upper safe area (~y: 280-500px)

## Dark Background Usage

When source footage is not vertical (9:16), use `assets/dark_bg1.mp4` as the background fill:

- **Resolution**: 432×768 at 30fps (scales cleanly to 1080×1920)
- **Duration**: 30 seconds — **must be looped** for longer compositions
- **Purpose**: Fills letterbox areas and provides a cohesive dark aesthetic
- **Scaling**: Scale to cover full 1080×1920 canvas, use `objectFit: "cover"`

### Layering Order (back to front)

1. **Dark background** (`dark_bg1.mp4`, looped)
2. **B-Roll / main content** (centered or positioned)
3. **A-Roll bubble** (if present, bottom-left)
4. **Text overlays** (hooks, captions, CTAs)
5. **Sound effect visuals** (optional flashes, emphasis)

## Alternate Layout: B-Roll Top + A-Roll Bottom

Use this format when you want both tracks visible at the same time.

### Vertical Split Zones (1080×1920)

| Zone         | X        | Y          | Width | Height | Content |
| ------------ | -------- | ---------- | ----- | ------ | ------- |
| Top panel    | 0        | 0          | 1080  | 960    | B-Roll  |
| Bottom panel | 0        | 960        | 1080  | 960    | A-Roll  |

### Placement Rules

- **B-Roll must stay in the top panel** (0-960px Y)
- **A-Roll must stay in the bottom panel** (960-1920px Y)
- Keep key faces/text away from the top unsafe area (~250px) and bottom unsafe area (~350px)
- If needed, reduce panel height for protected text areas and keep a center gutter (8-24px)

### Example Container Layout

```tsx
<AbsoluteFill>
  <div style={{ position: "absolute", top: 0, left: 0, width: 1080, height: 960 }}>
    <BRollTrack />
  </div>
  <div style={{ position: "absolute", top: 960, left: 0, width: 1080, height: 960 }}>
    <ARollTrack />
  </div>
</AbsoluteFill>
```

## Remotion Canvas Setup

```tsx
// In Root.tsx or similar
<Composition
  id="MainVideo"
  component={MainVideo}
  width={1080}
  height={1920}
  fps={30}
  durationInFrames={totalFrames}
/>
```
