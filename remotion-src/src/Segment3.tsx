// AUTO-GENERATED -- do not edit. Re-run via the trimmer UI to update.
import React from "react";
import { staticFile } from "remotion";
import { HalfAndHalf } from "./layouts/HalfAndHalf";

type SegmentTransforms = {
    aroll: { zoom: number; posX: number; posY: number };
    broll: { zoom: number; posX: number; posY: number };
};

export const Segment3: React.FC<{ splitRatio: number; visualTransforms: SegmentTransforms }> = ({ splitRatio, visualTransforms }) => (
  <HalfAndHalf
        arollSrc={staticFile("sports_production_aroll_seg003.mp4")}
        brollSrc={staticFile("sports_production_slap_seg001.mp4")}
    arollSourceSize={{ width: 1080, height: 1920 }}
    brollSourceSize={{ width: 1920, height: 1080 }}
    arollTrimStart={0}
    brollTrimStart={0}
    durationSec={3.694}
    splitRatio={splitRatio}
        arollTransform={visualTransforms.aroll}
        brollTransform={visualTransforms.broll}
    fps={30}
  />
);
