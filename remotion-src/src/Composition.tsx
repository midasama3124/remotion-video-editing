// AUTO-GENERATED -- do not edit. Re-run via the trimmer UI to update.
import React from "react";
import { Sequence } from "remotion";
import { Segment0 } from "./Segment0";
import { Segment1 } from "./Segment1";
import { Segment2 } from "./Segment2";

export const TOTAL_DURATION_FRAMES = 290;

type SegmentTransforms = {
  aroll: { zoom: number; posX: number; posY: number };
  broll: { zoom: number; posX: number; posY: number };
};

type Props = {
  segments: Array<{ splitRatio: number; visualTransforms: SegmentTransforms }>;
};

export const MyComposition: React.FC<Props> = ({ segments }) => (
  <>
    <Sequence durationInFrames={59}>
      <Segment0 splitRatio={segments[0].splitRatio} visualTransforms={segments[0].visualTransforms} />
    </Sequence>
    <Sequence from={59} durationInFrames={85}>
      <Segment1 splitRatio={segments[1].splitRatio} visualTransforms={segments[1].visualTransforms} />
    </Sequence>
    <Sequence from={144} durationInFrames={146}>
      <Segment2 visualTransforms={segments[2].visualTransforms} />
    </Sequence>
  </>
);
