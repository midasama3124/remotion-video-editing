import React from "react";
import { AbsoluteFill, Html5Video } from "remotion";

type VideoSize = {
  width: number;
  height: number;
};

type ARollOnlyProps = {
  arollSrc: string;
  arollTrimStart: number;
  durationSec: number;
  arollTransform?: {
    zoom: number;
    posX: number;
    posY: number;
  };
  arollSourceSize?: VideoSize;
  fps: number;
};

export const ARollOnly: React.FC<ARollOnlyProps> = ({
  arollSrc,
  arollTrimStart,
  durationSec,
  arollTransform = { zoom: 1, posX: 0, posY: 0 },
  arollSourceSize,
  fps,
}) => {
  const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
  const safeNumber = (value: number, fallback: number) => (Number.isFinite(value) ? value : fallback);

  const durationInFrames = Math.max(1, Math.round(durationSec * fps));
  const startAroll = Math.max(0, Math.round(arollTrimStart * fps));
  const endAroll = startAroll + durationInFrames;
  const viewportWidth = 1080;
  const viewportHeight = 1920;
  const sourceSize = arollSourceSize ?? { width: viewportWidth, height: viewportHeight };
  const zoom = Math.max(0.1, safeNumber(arollTransform.zoom, 1));
  const rawPosX = safeNumber(arollTransform.posX, 0);
  const rawPosY = safeNumber(arollTransform.posY, 0);
  const coverScale = Math.max(viewportWidth / sourceSize.width, viewportHeight / sourceSize.height);
  const drawW = sourceSize.width * coverScale;
  const drawH = sourceSize.height * coverScale;
  const maxOffsetX = Math.max(0, ((drawW * zoom) - viewportWidth) / 2);
  const maxOffsetY = Math.max(0, ((drawH * zoom) - viewportHeight) / 2);
  const safeArollTransform = {
    zoom,
    posX: clamp(rawPosX, -maxOffsetX, maxOffsetX),
    posY: clamp(rawPosY, -maxOffsetY, maxOffsetY),
  };

  return (
    <AbsoluteFill style={{ width: 1080, height: 1920, backgroundColor: "#000" }}>
      <div
        style={{
          width: "100%",
          height: "100%",
          transform: `translate(${safeArollTransform.posX}px, ${safeArollTransform.posY}px) scale(${safeArollTransform.zoom})`,
          transformOrigin: "center center",
        }}
      >
        <Html5Video
          src={arollSrc}
          startFrom={startAroll}
          endAt={endAroll}
          delayRenderTimeoutInMilliseconds={180000}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </div>
    </AbsoluteFill>
  );
};