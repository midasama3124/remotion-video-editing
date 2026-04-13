// AUTO-GENERATED -- do not edit. Re-run via the trimmer UI to update.
import React from "react";
import { staticFile } from "remotion";
import { BRollOnly } from "./layouts/BRollOnly";

type SegmentTransforms = {
    aroll: { zoom: number; posX: number; posY: number };
    broll: { zoom: number; posX: number; posY: number };
};

export const Segment2: React.FC<{ visualTransforms: SegmentTransforms }> = ({ visualTransforms }) => (
    <BRollOnly
        brollSrc={staticFile("sports_production_slap_seg000.mp4")}
        arollSrc={staticFile("sports_production_aroll_seg002.mp4")}
        brollSourceSize={{ width: 1920, height: 1080 }}
        arollSourceSize={{ width: 1080, height: 1920 }}
        brollTrimStart={0}
        arollTrimStart={0}
        durationSec={4.852}
        brollTransform={visualTransforms.broll}
        fps={30}
    />
);
