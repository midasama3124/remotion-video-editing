import React from "react";
import { AbsoluteFill, Video } from "remotion";

// Must match BASE_BUBBLE_RADIUS in trimmer_ui.html
const BASE_BUBBLE_RADIUS = 250;

type LayerTransform = {
  zoom: number;
  posX: number;
  posY: number;
};

type BubbleTransform = {
  posX: number;
  posY: number;
  zoom: number;
  softness: number;
};

type VideoSize = {
  width: number;
  height: number;
};

type BRollBubbleProps = {
  brollSrc: string;
  arollSrc: string;
  brollTrimStart: number;
  arollTrimStart: number;
  durationSec: number;
  brollTransform?: LayerTransform;
  arollTransform?: LayerTransform;
  bubbleTransform?: BubbleTransform;
  brollSourceSize?: VideoSize;
  arollSourceSize?: VideoSize;
  fps: number;
};

export const BRollBubble: React.FC<BRollBubbleProps> = ({
  brollSrc,
  arollSrc,
  brollTrimStart,
  arollTrimStart,
  durationSec,
  brollTransform = { zoom: 1, posX: 0, posY: 0 },
  arollTransform = { zoom: 1, posX: 0, posY: 0 },
  bubbleTransform = { posX: -270, posY: 700, zoom: 1.0, softness: 0.3 },
  brollSourceSize,
  arollSourceSize,
  fps,
}) => {
  const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
  const safeNumber = (value: number, fallback: number) => (Number.isFinite(value) ? value : fallback);

  const compositionWidth = 1080;
  const compositionHeight = 1920;
  const durationInFrames = Math.max(1, Math.round(durationSec * fps));
  const startBroll = Math.max(0, Math.round(brollTrimStart * fps));
  const endBroll = startBroll + durationInFrames;
  const startAroll = Math.max(0, Math.round(arollTrimStart * fps));
  const endAroll = startAroll + durationInFrames;

  // ── B-Roll background (full-frame cover-scale, mirrors BRollOnly.tsx) ──────
  const brollSource = brollSourceSize ?? { width: compositionWidth, height: compositionHeight };
  const brollZoom = Math.max(0.1, safeNumber(brollTransform.zoom, 1));
  const brollRawPosX = safeNumber(brollTransform.posX, 0);
  const brollRawPosY = safeNumber(brollTransform.posY, 0);
  const brollCoverScale = Math.max(compositionWidth / brollSource.width, compositionHeight / brollSource.height);
  const brollDrawW = brollSource.width * brollCoverScale;
  const brollDrawH = brollSource.height * brollCoverScale;
  const brollMaxOffsetX = Math.abs(((brollDrawW * brollZoom) - compositionWidth) / 2);
  const brollMaxOffsetY = Math.abs(((brollDrawH * brollZoom) - compositionHeight) / 2);
  const safeBrollTransform = {
    zoom: brollZoom,
    posX: clamp(brollRawPosX, -brollMaxOffsetX, brollMaxOffsetX),
    posY: clamp(brollRawPosY, -brollMaxOffsetY, brollMaxOffsetY),
  };

  // ── Bubble geometry ───────────────────────────────────────────────────────
  const bubbleZoom = Math.max(0.1, safeNumber(bubbleTransform.zoom, 1));
  const bubbleRadius = Math.round(BASE_BUBBLE_RADIUS * bubbleZoom);
  const bubbleDiameter = bubbleRadius * 2;
  const bubbleCenterX = compositionWidth / 2 + safeNumber(bubbleTransform.posX, -270);
  const bubbleCenterY = compositionHeight / 2 + safeNumber(bubbleTransform.posY, 700);
  // softness ∈ [0, 1]: 0 = hard edge, 1 = fully faded from center to edge.
  // The radial gradient hard-stop percentage = (1 - softness) * 100%.
  const bubbleSoftness = clamp(safeNumber(bubbleTransform.softness, 0.3), 0, 1);
  const hardStopPct = Math.max(0, (1 - bubbleSoftness) * 100).toFixed(1);

  // CSS mask applied to A-roll wrapper (square div = bubbleDiameter × bubbleDiameter).
  // "circle closest-side" makes the gradient reach to the midpoint of each side = bubbleRadius,
  // so the gradient matches the circle geometry exactly.
  const maskStyle: React.CSSProperties =
    bubbleSoftness > 0
      ? {
          WebkitMaskImage: `radial-gradient(circle closest-side, black ${hardStopPct}%, transparent 100%)`,
          maskImage: `radial-gradient(circle closest-side, black ${hardStopPct}%, transparent 100%)`,
        }
      : {};

  // ── A-Roll content inside bubble (square panel = bubbleDiameter × bubbleDiameter) ─
  // Mirrors computeLayer() from HalfAndHalf.tsx.
  const arollSource = arollSourceSize ?? { width: compositionWidth, height: compositionHeight };
  const arollZoom = Math.max(0.1, safeNumber(arollTransform.zoom, 1));
  const arollRawPosX = safeNumber(arollTransform.posX, 0);
  const arollRawPosY = safeNumber(arollTransform.posY, 0);

  const arollCoverScale = Math.max(bubbleDiameter / arollSource.width, bubbleDiameter / arollSource.height);
  const arollCoveredW = arollSource.width * arollCoverScale;
  const arollCoveredH = arollSource.height * arollCoverScale;
  const arollMaxOffsetX = Math.max(0, (arollCoveredW * arollZoom - bubbleDiameter) / 2);
  const arollMaxOffsetY = Math.max(0, (arollCoveredH * arollZoom - bubbleDiameter) / 2);
  const arollPosX = clamp(arollRawPosX, -arollMaxOffsetX, arollMaxOffsetX);
  const arollPosY = clamp(arollRawPosY, -arollMaxOffsetY, arollMaxOffsetY);
  const arollLeft = (bubbleDiameter - arollCoveredW) / 2;
  const arollTop = (bubbleDiameter - arollCoveredH) / 2;

  const bubbleLeft = bubbleCenterX - bubbleRadius;
  const bubbleTop = bubbleCenterY - bubbleRadius;

  return (
    <AbsoluteFill style={{ width: compositionWidth, height: compositionHeight, backgroundColor: "#000" }}>
      {/* B-Roll — full-frame background (muted) */}
      <div
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          transform: `translate(${safeBrollTransform.posX}px, ${safeBrollTransform.posY}px) scale(${safeBrollTransform.zoom})`,
          transformOrigin: "center center",
        }}
      >
        <Video
          src={brollSrc}
          startFrom={startBroll}
          endAt={endBroll}
          delayRenderTimeoutInMilliseconds={180000}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
          muted
        />
      </div>

      {/* Bubble container — hard circle clip via overflow:hidden + border-radius; NO mask here */}
      <div
        style={{
          position: "absolute",
          left: `${bubbleLeft}px`,
          top: `${bubbleTop}px`,
          width: `${bubbleDiameter}px`,
          height: `${bubbleDiameter}px`,
          borderRadius: "50%",
          overflow: "hidden",
          zIndex: 2,
        }}
      >
        {/* B-Roll copy — same pixels as full-frame B-roll, offset so composition coords align */}
        <div
          style={{
            position: "absolute",
            left: `${-bubbleLeft}px`,
            top: `${-bubbleTop}px`,
            width: `${compositionWidth}px`,
            height: `${compositionHeight}px`,
            transform: `translate(${safeBrollTransform.posX}px, ${safeBrollTransform.posY}px) scale(${safeBrollTransform.zoom})`,
            transformOrigin: "center center",
          }}
        >
          <Video
            src={brollSrc}
            startFrom={startBroll}
            endAt={endBroll}
            delayRenderTimeoutInMilliseconds={180000}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            muted
          />
        </div>

        {/* A-Roll mask wrapper — mask-image here fades A-roll into B-roll copy (same stacking context) */}
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            width: "100%",
            height: "100%",
            ...maskStyle,
          }}
        >
          {/* Inner positioned div for cover-scale + arollTransform */}
          <div
            style={{
              position: "absolute",
              left: `${arollLeft}px`,
              top: `${arollTop}px`,
              width: `${arollCoveredW}px`,
              height: `${arollCoveredH}px`,
              transform: `translate(${arollPosX}px, ${arollPosY}px) scale(${arollZoom})`,
              transformOrigin: "center center",
            }}
          >
            {/* A-Roll video — visible (audio source) inside the bubble */}
            <Video
              src={arollSrc}
              startFrom={startAroll}
              endAt={endAroll}
              delayRenderTimeoutInMilliseconds={180000}
              style={{ width: "100%", height: "100%", objectFit: "fill" }}
            />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
