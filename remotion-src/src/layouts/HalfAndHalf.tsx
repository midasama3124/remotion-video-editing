import React from "react";
import { AbsoluteFill, Html5Video } from "remotion";

type LayerTransform = {
  zoom: number;
  posX: number;
  posY: number;
};

type VideoSize = {
  width: number;
  height: number;
};

type HalfAndHalfProps = {
  arollSrc: string;
  brollSrc: string;
  arollTrimStart: number;
  brollTrimStart: number;
  durationSec: number;
  splitRatio?: number;
  arollTransform?: LayerTransform;
  brollTransform?: LayerTransform;
  arollSourceSize?: VideoSize;
  brollSourceSize?: VideoSize;
  fps: number;
};

export const HalfAndHalf: React.FC<HalfAndHalfProps> = ({
  arollSrc,
  brollSrc,
  arollTrimStart,
  brollTrimStart,
  durationSec,
  splitRatio = 0.5,
  arollTransform = { zoom: 1, posX: 0, posY: 0 },
  brollTransform = { zoom: 1, posX: 0, posY: 0 },
  arollSourceSize,
  brollSourceSize,
  fps,
}) => {
  const clamp = (value: number, min: number, max: number) =>
    Math.min(max, Math.max(min, value));
  const safeNumber = (value: number, fallback: number) =>
    Number.isFinite(value) ? value : fallback;

  const safeSplitRatio = Math.min(1, Math.max(0, splitRatio));
  const durationInFrames = Math.max(1, Math.round(durationSec * fps));
  const startAroll = Math.max(0, Math.round(arollTrimStart * fps));
  const startBroll = Math.max(0, Math.round(brollTrimStart * fps));
  const endAroll = startAroll + durationInFrames;
  const endBroll = startBroll + durationInFrames;

  const compositionWidth = 1080;
  const compositionHeight = 1920;
  const topHeightPx = Math.floor(safeSplitRatio * compositionHeight);
  const bottomTopPx = topHeightPx;
  const bottomHeightPx = compositionHeight - topHeightPx;

  // -- Helper: compute absolute position/size for a video layer --
  // This replicates the canvas preview exactly:
  //   1. Scale source video to "cover" the panel (no black bars at zoom=1)
  //   2. Apply user zoom on top of cover scale
  //   3. Center in panel, then offset by posX/posY
  // The panel's overflow:hidden provides the clip - identical to ctx.clip()
  // in the canvas. objectFit is NOT used so the element itself is never
  // clipped before posX/posY are applied.
  const computeVideoLayout = (
    panelW: number,
    panelH: number,
    sourceSize: VideoSize,
    transform: LayerTransform,
  ) => {
    const zoom = Math.max(0.1, safeNumber(transform.zoom, 1));
    const rawPosX = safeNumber(transform.posX, 0);
    const rawPosY = safeNumber(transform.posY, 0);

    const coverScale = Math.max(
      panelW / sourceSize.width,
      panelH / sourceSize.height,
    );
    const scaledW = sourceSize.width * coverScale * zoom;
    const scaledH = sourceSize.height * coverScale * zoom;

    // Clamp so the video always fully covers the panel (no black bars)
    const maxOffsetX = Math.max(0, (scaledW - panelW) / 2);
    const maxOffsetY = Math.max(0, (scaledH - panelH) / 2);
    const posX = clamp(rawPosX, -maxOffsetX, maxOffsetX);
    const posY = clamp(rawPosY, -maxOffsetY, maxOffsetY);

    return {
      width: scaledW,
      height: scaledH,
      left: (panelW - scaledW) / 2 + posX,
      top: (panelH - scaledH) / 2 + posY,
    };
  };

  const fallbackBrollSize: VideoSize = {
    width: compositionWidth,
    height: Math.max(1, topHeightPx),
  };
  const fallbackArollSize: VideoSize = {
    width: compositionWidth,
    height: Math.max(1, bottomHeightPx),
  };

  const brollLayout = computeVideoLayout(
    compositionWidth,
    topHeightPx,
    brollSourceSize ?? fallbackBrollSize,
    brollTransform,
  );
  const arollLayout = computeVideoLayout(
    compositionWidth,
    bottomHeightPx,
    arollSourceSize ?? fallbackArollSize,
    arollTransform,
  );

  return (
    <AbsoluteFill style={{ width: 1080, height: 1920, backgroundColor: "#000" }}>
      {/* -- B-Roll (top panel) -- */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 0,
          height: `${topHeightPx}px`,
          overflow: "hidden",
          zIndex: 1,
        }}
      >
        <Html5Video
          src={brollSrc}
          startFrom={startBroll}
          endAt={endBroll}
          onError={(error) => {
            console.error("B-roll playback error", { src: brollSrc, error });
          }}
          style={{
            position: "absolute",
            width: `${brollLayout.width}px`,
            height: `${brollLayout.height}px`,
            left: `${brollLayout.left}px`,
            top: `${brollLayout.top}px`,
          }}
        />
      </div>

      {/* -- A-Roll (bottom panel) -- */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: `${bottomTopPx}px`,
          height: `${bottomHeightPx}px`,
          overflow: "hidden",
          zIndex: 1,
        }}
      >
        <Html5Video
          src={arollSrc}
          startFrom={startAroll}
          endAt={endAroll}
          onError={(error) => {
            console.error("A-roll playback error", { src: arollSrc, error });
          }}
          style={{
            position: "absolute",
            width: `${arollLayout.width}px`,
            height: `${arollLayout.height}px`,
            left: `${arollLayout.left}px`,
            top: `${arollLayout.top}px`,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
