// AUTO-GENERATED -- do not edit. Re-run via the trimmer UI to update.
import React from "react";
import { Sequence } from "remotion";
import { Segment0 } from "./Segment0";
import { Segment1 } from "./Segment1";

export const TOTAL_DURATION_FRAMES = 144;

type Props = {
  segments: Array<{ splitRatio: number }>;
};

export const MyComposition: React.FC<Props> = ({ segments }) => (
  <>
    <Sequence durationInFrames={59}>
      <Segment0 splitRatio={segments[0].splitRatio} />
    </Sequence>
    <Sequence from={59} durationInFrames={85}>
      <Segment1 splitRatio={segments[1].splitRatio} />
    </Sequence>
  </>
);
