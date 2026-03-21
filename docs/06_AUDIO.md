# Audio Guidelines

## Audio Layers

Every video has up to 4 audio layers, mixed together:

| Layer | Source                | Priority | Typical Volume |
| ----- | --------------------- | -------- | -------------- |
| 1     | A-Roll narration      | Highest  | 100%           |
| 2     | Background music      | Low      | 15-25%         |
| 3     | Sound effects (SFX)   | Medium   | 40-70%         |
| 4     | B-Roll ambient audio  | Lowest   | 0-10%          |

## Layer 1: A-Roll Narration

- Extracted from the A-Roll video file
- This is the **primary audio track** — everything else is mixed around it
- Should be consistent in volume throughout (normalize if needed)
- Never ducked or reduced for other layers

```tsx
<OffthreadVideo
  src={staticFile("video/aroll.mp4")}
  startFrom={trimStart}
  volume={1}   // Full volume
/>
```

When A-Roll is in bubble mode and the video is visually hidden in some sections, **the audio should still play continuously**.

## Layer 2: Background Music

Source from `assets/soundtrack/`:

| Track                          | Mood                   | BPM (approx) |
| ------------------------------ | ---------------------- | ------------- |
| GLORY - Ogryzek.mp3           | Epic, cinematic        | ~130          |
| Life's Journey Begins - idokay.mp3 | Uplifting, motivational | ~110      |

### Music Mixing Rules

- Volume at **15-25%** (0.15-0.25) so narration is clearly audible
- **Fade in** over 0.5-1s at the start of the video
- **Fade out** over 1-2s at the end
- Consider **ducking** during key narration moments (lower to 10%)

```tsx
<Audio
  src={staticFile("../assets/soundtrack/GLORY - Ogryzek.mp3")}
  volume={(f) => {
    const { fps, durationInFrames } = useVideoConfig();
    // Fade in over 0.5s, sustain, fade out over 1s
    const fadeIn = interpolate(f, [0, fps * 0.5], [0, 0.2], { extrapolateRight: "clamp" });
    const fadeOut = interpolate(f, [durationInFrames - fps, durationInFrames], [0.2, 0], { extrapolateLeft: "clamp" });
    return Math.min(fadeIn, fadeOut);
  }}
  startFrom={musicTrimStart}
/>
```

### Music Selection Criteria

- Choose based on video mood and pacing
- Faster BPM for energetic product showcases
- Slower BPM for emotional or storytelling content
- Music should enhance cuts — try to align major cuts to musical beats

## Layer 3: Sound Effects (SFX)

Source from `assets/sound_effects/`. These punctuate key moments:

| SFX File                       | Use Case                                      |
| ------------------------------ | --------------------------------------------- |
| Cinematic Boom.mp3             | Opening impact, major reveal                  |
| bass_sharp_detail_riser.mp3    | Building tension before a reveal              |
| digital_camera_shutter.mp3     | Screenshot moment, feature highlight          |
| jaws.mp3                       | Dramatic tension, surprising reveal           |
| modern_select.mp3              | UI interaction, menu navigation               |
| riser_effects.mp3              | Tension build, approaching a climax           |
| short_select.mp3               | Quick tap, feature selection                  |

### SFX Placement Rules

- Place **on scene changes** that need emphasis (not every cut)
- **Riser/build** SFX start 0.5-1s before the reveal they lead into
- **Impact** SFX land exactly on the cut frame
- Max **3-5 SFX per 15 seconds** — overuse reduces impact
- Volume varies by effect: booms at 50-70%, subtle selects at 30-50%

```tsx
<Sequence from={impactFrame - 15} durationInFrames={60} premountFor={30}>
  <Audio
    src={staticFile("../assets/sound_effects/Cinematic Boom.mp3")}
    volume={0.6}
  />
</Sequence>
```

## Layer 4: B-Roll Ambient Audio

- **Muted by default** (`volume={0}`)
- Only include when the B-Roll has meaningful audio (product demo sounds, UI clicks)
- When included, keep at 5-10% volume so it doesn't compete with narration

## Master Volume Checklist

Before rendering, verify:

- [ ] A-Roll narration is clear and undistorted across all sections
- [ ] Background music is audible but doesn't overpower narration
- [ ] SFX are impactful but not jarring
- [ ] No audio pops or clicks at cut points
- [ ] Fade in/out at video start and end
- [ ] B-Roll audio is silenced unless intentionally included

## Alternate Format: Audio in B-Roll Top / A-Roll Bottom Layout

The visual placement changes, but core audio priority remains the same.

### Mix Behavior

- **A-Roll narration remains the anchor track** at full clarity
- **Top B-Roll panel** stays muted by default (`volume={0}`)
- Music and SFX timing should align with top-panel cut rhythm
- If bottom A-Roll panel is visually static, keep using SFX sparingly to avoid over-styling

### Practical Rule

When both panels are visible simultaneously, do not duplicate spoken content with text and loud SFX at the same moment. Keep one focal cue at a time:

1. narration,
2. or SFX accent,
3. or music build.
