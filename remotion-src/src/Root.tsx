import "./index.css";
import { Composition } from "remotion";
import { MyComposition, TOTAL_DURATION_FRAMES } from "./Composition";
import inputProps from "./inputProps.json";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="MyVideo"
        component={MyComposition}
        durationInFrames={TOTAL_DURATION_FRAMES}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={inputProps}
      />
    </>
  );
};
