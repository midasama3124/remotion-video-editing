// AUTO-GENERATED -- do not edit. Re-run via the trimmer UI to update.
import React from "react";
import { staticFile } from "remotion";
import { ARollOnly } from "./layouts/ARollOnly";

type SegmentTransforms = {
    aroll: { zoom: number; posX: number; posY: number };
    broll: { zoom: number; posX: number; posY: number };
};

export const Segment2: React.FC<{ visualTransforms: SegmentTransforms }> = ({ visualTransforms }) => (
    <ARollOnly
        arollSrc={staticFile("sports_production_aroll_seg002.mp4")}
        arollTrimStart={0}
        durationSec={4.852}
        arollTransform={visualTransforms.aroll}
        fps={30}
    />
);
