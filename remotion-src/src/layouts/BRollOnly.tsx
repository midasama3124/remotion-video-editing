import React from "react";
import { AbsoluteFill, Video } from "remotion";

type VideoSize = {
  width: number;
  height: number;
};

type BRollOnlyProps = {
  brollSrc: string;
  arollSrc: string;
  brollTrimStart: number;
  arollTrimStart: number;
  durationSec: number;
  brollTransform?: {
    zoom: number;
    posX: number;
    posY: number;
  };
  brollSourceSize?: VideoSize;
  arollSourceSize?: VideoSize;
  fps: number;
};

export const BRollOnly: React.FC<BRollOnlyProps> = ({
  brollSrc,
  arollSrc,
  brollTrimStart,
  arollTrimStart,
  durationSec,
  brollTransform = { zoom: 1, posX: 0, posY: 0 },
  brollSourceSize,
  fps,
}) => {
  const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
  const safeNumber = (value: number, fallback: number) => (Number.isFinite(value) ? value : fallback);

  const durationInFrames = Math.max(1, Math.round(durationSec * fps));
  const startBroll = Math.max(0, Math.round(brollTrimStart * fps));
  const endBroll = startBroll + durationInFrames;
  const startAroll = Math.max(0, Math.round(arollTrimStart * fps));
  const endAroll = startAroll + durationInFrames;
  const viewportWidth = 1080;
  const viewportHeight = 1920;
  const sourceSize = brollSourceSize ?? { width: viewportWidth, height: viewportHeight };
  const zoom = Math.max(0.1, safeNumber(brollTransform.zoom, 1));
  const rawPosX = safeNumber(brollTransform.posX, 0);
  const rawPosY = safeNumber(brollTransform.posY, 0);
  const coverScale = Math.max(viewportWidth / sourceSize.width, viewportHeight / sourceSize.height);
  const drawW = sourceSize.width * coverScale;
  const drawH = sourceSize.height * coverScale;
  const maxOffsetX = Math.abs(((drawW * zoom) - viewportWidth) / 2);
  const maxOffsetY = Math.abs(((drawH * zoom) - viewportHeight) / 2);
  const safeBrollTransform = {
    zoom,
    posX: clamp(rawPosX, -maxOffsetX, maxOffsetX),
    posY: clamp(rawPosY, -maxOffsetY, maxOffsetY),
  };

  return (
    <AbsoluteFill style={{ width: 1080, height: 1920, backgroundColor: "#000" }}>
      {/* A-Roll audio source — rendered invisibly so only its audio plays */}
      <Video
        src={arollSrc}
        startFrom={startAroll}
        endAt={endAroll}
        delayRenderTimeoutInMilliseconds={180000}
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          opacity: 0,
          pointerEvents: "none",
        }}
      />
      {/* B-Roll visual — full frame */}
      <div
        style={{
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
    </AbsoluteFill>
  );
};
