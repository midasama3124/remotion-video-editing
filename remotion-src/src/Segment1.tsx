// AUTO-GENERATED -- do not edit. Re-run via the trimmer UI to update.
import React from "react";
import { staticFile } from "remotion";
import { HalfAndHalf } from "./layouts/HalfAndHalf";

export const Segment1: React.FC<{ splitRatio: number }> = ({ splitRatio }) => (
  <HalfAndHalf
        arollSrc={staticFile("sports_production_aroll_seg001.mp4")}
        brollSrc={staticFile("sports_production_broll_seg001.mp4")}
    arollTrimStart={0}
    brollTrimStart={0}
    durationSec={2.835}
    splitRatio={splitRatio}
    fps={30}
  />
);
