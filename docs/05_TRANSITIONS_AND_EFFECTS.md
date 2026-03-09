# Transitions & Visual Effects

## Transition Types

### 1. Hard Cut (Default)

Direct cut between clips with no effect. Used for:
- Fast-paced montages
- Maintaining energy and rhythm
- Most B-Roll to B-Roll transitions

This is the **dominant transition style** in the reference. ~80% of transitions are hard cuts.

### 2. Dark Flash / Black Frame

A brief dark frame (2-6 frames / 0.07-0.2s) between clips. Used for:
- Topic changes within the video
- Separating narrative beats
- Adding dramatic weight to a statement

```tsx
<Sequence from={cutPoint - 3} durationInFrames={6} premountFor={10}>
  <AbsoluteFill style={{ backgroundColor: "black" }} />
</Sequence>
```

### 3. Fade to/from Black

Slightly longer than dark flash (10-15 frames / 0.33-0.5s). Used for:
- Major section transitions
- Opening and closing the video

```tsx
const frame = useCurrentFrame();
const opacity = interpolate(frame, [0, 15], [1, 0], {
  extrapolateRight: "clamp",
});

<AbsoluteFill style={{ backgroundColor: "black", opacity }} />
```

### 4. Scale Transition

The incoming clip scales from ~0.8x to 1x. Used for:
- Revealing a new B-Roll clip with energy
- Making a cut feel more dynamic

```tsx
const frame = useCurrentFrame();
const scale = spring({ frame, fps: 30, config: { damping: 200 } });
const scaleValue = interpolate(scale, [0, 1], [0.85, 1]);

<div style={{ transform: `scale(${scaleValue})` }}>
  <BRollClip />
</div>
```

### 5. Whip Pan / Slide

The outgoing clip slides out while the incoming clip slides in. Used sparingly for:
- Showing before/after
- Comparing features

Using Remotion's `@remotion/transitions`:

```tsx
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { slide } from "@remotion/transitions/slide";

<TransitionSeries>
  <TransitionSeries.Sequence durationInFrames={90}>
    <ClipA />
  </TransitionSeries.Sequence>
  <TransitionSeries.Transition
    presentation={slide({ direction: "from-left" })}
    timing={linearTiming({ durationInFrames: 8 })}
  />
  <TransitionSeries.Sequence durationInFrames={90}>
    <ClipB />
  </TransitionSeries.Sequence>
</TransitionSeries>
```

## Visual Effects

### Text Overlays / Hook Text

Bold text that appears during the first 1-3 seconds to hook the viewer.

```tsx
<div
  style={{
    position: "absolute",
    top: 300,            // Within safe zone
    left: 60,
    right: 60,
    textAlign: "center",
    fontFamily: "Inter, sans-serif",
    fontWeight: 900,
    fontSize: 64,
    color: "white",
    textShadow: "0 2px 8px rgba(0,0,0,0.8)",
    lineHeight: 1.2,
  }}
>
  HOOK TEXT HERE
</div>
```

### Emphasis Flash

A brief white or colored flash on beat with music or SFX:

```tsx
const frame = useCurrentFrame();
const opacity = interpolate(frame, [0, 2, 6], [0, 0.3, 0], {
  extrapolateRight: "clamp",
});

<AbsoluteFill style={{ backgroundColor: "white", opacity }} />
```

### Zoom Punch

Quick zoom-in on a B-Roll frame for emphasis:

```tsx
const frame = useCurrentFrame();
const scale = spring({ frame, fps: 30, config: { damping: 12, stiffness: 200 } });
const scaleValue = interpolate(scale, [0, 1], [1, 1.15]);

<div style={{ transform: `scale(${scaleValue})`, transformOrigin: "center center" }}>
  <BRollClip />
</div>
```

## Transition Rhythm

The pacing of transitions should match the audio rhythm:

- **On the beat**: Align hard cuts with music beats or SFX hits
- **On narration pauses**: Use dark flashes on natural speech pauses
- **Building energy**: Decrease cut duration toward a climax, then release with a longer cut

### Timing Table

| Transition        | Duration (frames) | Duration (sec) | Energy Level |
| ----------------- | ------------------ | -------------- | ------------ |
| Hard cut          | 0                  | 0              | Neutral      |
| Dark flash        | 2-6                | 0.07-0.2       | Medium       |
| Fade to black     | 10-15              | 0.33-0.5       | Low          |
| Scale in          | 8-12               | 0.27-0.4       | High         |
| Slide             | 6-10               | 0.2-0.33       | High         |
| Emphasis flash    | 4-8                | 0.13-0.27      | High         |
