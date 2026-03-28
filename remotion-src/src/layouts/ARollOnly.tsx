import React from "react";
import { AbsoluteFill, Html5Video } from "remotion";

type ARollOnlyProps = {
  arollSrc: string;
  arollTrimStart: number;
  durationSec: number;
  fps: number;
};

export const ARollOnly: React.FC<ARollOnlyProps> = ({
  arollSrc,
  arollTrimStart,
  durationSec,
  fps,
}) => {
  const durationInFrames = Math.max(1, Math.round(durationSec * fps));
  const startAroll = Math.max(0, Math.round(arollTrimStart * fps));
  const endAroll = startAroll + durationInFrames;

  return (
    <AbsoluteFill style={{ width: 1080, height: 1920, backgroundColor: "#000" }}>
      <Html5Video
        src={arollSrc}
        startFrom={startAroll}
        endAt={endAroll}
        onError={(error) => {
          console.error("A-roll playback error", { src: arollSrc, error });
        }}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};