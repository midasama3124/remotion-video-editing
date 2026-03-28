import React from "react";
import { AbsoluteFill, Html5Video } from "remotion";

type LayerTransform = {
  zoom: number;
  posX: number;
  posY: number;
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
  fps,
}) => {
  const safeSplitRatio = Math.min(1, Math.max(0, splitRatio));
  const durationInFrames = Math.max(1, Math.round(durationSec * fps));
  const startAroll = Math.max(0, Math.round(arollTrimStart * fps));
  const startBroll = Math.max(0, Math.round(brollTrimStart * fps));
  const endAroll = startAroll + durationInFrames;
  const endBroll = startBroll + durationInFrames;
  const topHeight = `${safeSplitRatio * 100}%`;
  const bottomHeight = `${(1 - safeSplitRatio) * 100}%`;

  return (
    <AbsoluteFill style={{ width: 1080, height: 1920, backgroundColor: "#000" }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 0,
          height: topHeight,
          overflow: "hidden",
          zIndex: 1,
        }}
      >
        <div
          style={{
            width: "100%",
            height: "100%",
            transform: `translate(${brollTransform.posX}px, ${brollTransform.posY}px) scale(${brollTransform.zoom})`,
            transformOrigin: "center center",
          }}
        >
          <Html5Video
            src={brollSrc}
            startFrom={startBroll}
            endAt={endBroll}
            onError={(error) => {
              console.error("B-roll playback error", { src: brollSrc, error });
            }}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: bottomHeight,
          overflow: "hidden",
          zIndex: 1,
        }}
      >
        <div
          style={{
            width: "100%",
            height: "100%",
            transform: `translate(${arollTransform.posX}px, ${arollTransform.posY}px) scale(${arollTransform.zoom})`,
            transformOrigin: "center center",
          }}
        >
          <Html5Video
            src={arollSrc}
            startFrom={startAroll}
            endAt={endAroll}
            onError={(error) => {
              console.error("A-roll playback error", { src: arollSrc, error });
            }}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
