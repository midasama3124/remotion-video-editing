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
  arollSourceSize = { width: 1080, height: 1920 },
  brollSourceSize = { width: 1920, height: 1080 },
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

  // Mirrors drawVideoCoverWithTransform exactly:
  //   coverScale = max(panelW/srcW, panelH/srcH)
  //   drawW = srcW * coverScale  (no zoom — zoom applied via ctx.scale)
  //   drawH = srcH * coverScale
  //   maxOffsetX = max(0, (drawW*zoom - panelW) / 2)
  //   ctx.translate(panelCX + posX, panelCY + posY)
  //   ctx.scale(zoom, zoom)
  //   ctx.drawImage(video, -drawW/2, -drawH/2, drawW, drawH)
  //
  // CSS equivalent:
  //   Inner div sized to drawW × drawH, centered in panel.
  //   transform: translate(posX, posY) scale(zoom) with transformOrigin: center center
  //   Video: width/height 100%, objectFit: fill  (div already has correct aspect ratio)
  const computeLayer = (
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
    const coveredW = sourceSize.width * coverScale;
    const coveredH = sourceSize.height * coverScale;

    const maxOffsetX = Math.max(0, (coveredW * zoom - panelW) / 2);
    const maxOffsetY = Math.max(0, (coveredH * zoom - panelH) / 2);
    const posX = clamp(rawPosX, -maxOffsetX, maxOffsetX);
    const posY = clamp(rawPosY, -maxOffsetY, maxOffsetY);

    // Position inner div: centered in panel
    const left = (panelW - coveredW) / 2;
    const top = (panelH - coveredH) / 2;

    return { coveredW, coveredH, left, top, zoom, posX, posY };
  };

  const broll = computeLayer(compositionWidth, topHeightPx, brollSourceSize, brollTransform);
  const aroll = computeLayer(compositionWidth, bottomHeightPx, arollSourceSize, arollTransform);

  const videoStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    objectFit: "fill",
  };

  return (
    <AbsoluteFill style={{ width: 1080, height: 1920, backgroundColor: "#000" }}>
      {/* B-Roll (top panel) */}
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
        <div
          style={{
            position: "absolute",
            left: `${broll.left}px`,
            top: `${broll.top}px`,
            width: `${broll.coveredW}px`,
            height: `${broll.coveredH}px`,
            transform: `translate(${broll.posX}px, ${broll.posY}px) scale(${broll.zoom})`,
            transformOrigin: "center center",
          }}
        >
          <Html5Video
            src={brollSrc}
            startFrom={startBroll}
            endAt={endBroll}
            delayRenderTimeoutInMilliseconds={180000}
            style={videoStyle}
          />
        </div>
      </div>

      {/* A-Roll (bottom panel) */}
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
        <div
          style={{
            position: "absolute",
            left: `${aroll.left}px`,
            top: `${aroll.top}px`,
            width: `${aroll.coveredW}px`,
            height: `${aroll.coveredH}px`,
            transform: `translate(${aroll.posX}px, ${aroll.posY}px) scale(${aroll.zoom})`,
            transformOrigin: "center center",
          }}
        >
          <Html5Video
            src={arollSrc}
            startFrom={startAroll}
            endAt={endAroll}
            delayRenderTimeoutInMilliseconds={180000}
            style={videoStyle}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
