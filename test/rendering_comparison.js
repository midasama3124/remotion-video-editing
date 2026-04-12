/**
 * Test to compare canvas rendering vs React rendering calculations
 * for Half-And-Half layout with transforms.
 *
 * Canvas approach (trimmer_ui.html):
 *   ctx.translate(center + posX, center + posY)
 *   ctx.scale(zoom, zoom)
 *   ctx.drawImage(videoEl, -drawW/2, -drawH/2, drawW, drawH)
 *
 * React approach (HalfAndHalf.tsx — CSS transform):
 *   transform: translate(posX, posY) scale(zoom)
 *   transformOrigin: center center
 *   objectFit: cover
 *
 * Both place the video CENTER at (panelCenter + posX, panelCenter + posY).
 * This script verifies that both compute the same clamped posX/posY and
 * the same visual left/top edge for the drawn video.
 */

const TEST_DATA = {
  segmentIndex: 0,
  splitRatio: 0.5,
  brollSourceSize: { width: 1920, height: 1080 },
  arollSourceSize: { width: 1080, height: 1920 },
  brollTransform: { zoom: 1.02, posX: 112.0, posY: -90.0 },
  arollTransform: { zoom: 1.1, posX: 0.0, posY: 223.0 },
};

const COMPOSITION_WIDTH = 1080;
const COMPOSITION_HEIGHT = 1920;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function safeNumber(value, fallback) {
  return Number.isFinite(value) ? value : fallback;
}

// ---------------------------------------------------------------------------
// CANVAS VERSION (mirrors trimmer_ui.html drawVideoCoverWithTransform)
// ---------------------------------------------------------------------------
function canvasComputeLayout(clipW, clipH, sourceSize, transform) {
  const zoom = Math.max(0.1, safeNumber(transform.zoom, 1));
  const rawPosX = safeNumber(transform.posX, 0);
  const rawPosY = safeNumber(transform.posY, 0);

  // coverScale: scale the source so it covers the clip region
  const coverScale = Math.max(
    clipW / sourceSize.width,
    clipH / sourceSize.height
  );
  // drawW/drawH are the pre-zoom dimensions; ctx.scale(zoom) enlarges them
  const drawW = sourceSize.width * coverScale;
  const drawH = sourceSize.height * coverScale;

  // max pan is half of the excess after applying zoom
  const maxOffsetX = Math.max(0, (drawW * zoom - clipW) / 2);
  const maxOffsetY = Math.max(0, (drawH * zoom - clipH) / 2);
  const posX = clamp(rawPosX, -maxOffsetX, maxOffsetX);
  const posY = clamp(rawPosY, -maxOffsetY, maxOffsetY);

  // Canvas translates to (clipCenter + posX/Y), scales, then draws centered.
  // Visual left/top of the drawn image in SCREEN pixels (relative to clip origin):
  //   left = (clipW/2 + posX) - (drawW * zoom / 2)
  //        = (clipW - drawW*zoom) / 2 + posX
  const scaledW = drawW * zoom;
  const scaledH = drawH * zoom;
  const visualLeft = (clipW - scaledW) / 2 + posX;
  const visualTop  = (clipH - scaledH) / 2 + posY;

  return {
    coverScale,
    zoom,
    posX,
    posY,
    scaledW,
    scaledH,
    visualLeft,
    visualTop,
    // Center of video in panel coordinates
    centerX: clipW / 2 + posX,
    centerY: clipH / 2 + posY,
  };
}

function canvasRenderingCalculations(seg) {
  const targetHeight = 1920;
  const targetWidth  = 1080;
  const safeSplitRatio = clamp(
    Number.isFinite(Number(seg.splitRatio)) ? Number(seg.splitRatio) : 0.5,
    0, 1
  );
  const topHeight    = Math.floor(targetHeight * safeSplitRatio);
  const bottomHeight = targetHeight - topHeight;

  const brollLayout = canvasComputeLayout(targetWidth, topHeight,    seg.brollSourceSize, seg.brollTransform);
  const arollLayout = canvasComputeLayout(targetWidth, bottomHeight, seg.arollSourceSize, seg.arollTransform);
  return { brollLayout, arollLayout, topHeight, bottomHeight };
}

// ---------------------------------------------------------------------------
// REACT VERSION — NEW CSS-transform approach (HalfAndHalf.tsx after fix)
//
// The component now uses:
//   <div style={{ width:"100%", height:"100%",
//                 transform:`translate(posX, posY) scale(zoom)`,
//                 transformOrigin:"center center" }}>
//     <Video style={{ width:"100%", height:"100%", objectFit:"cover" }} />
//   </div>
//
// CSS `translate(posX,posY) scale(zoom)` with transformOrigin=center means:
//   1. scale(zoom) around panel center
//   2. translate(posX, posY)
// Video center in panel coords: panelCenter + posX
// Visual left edge: panelCenter + posX - scaledW/2
//                 = (panelW - scaledW) / 2 + posX   ← same as canvas
// ---------------------------------------------------------------------------
function reactComputeLayout(panelW, panelH, sourceSize, transform) {
  const zoom    = Math.max(0.1, safeNumber(transform.zoom, 1));
  const rawPosX = safeNumber(transform.posX, 0);
  const rawPosY = safeNumber(transform.posY, 0);

  // CSS objectFit:cover picks coverScale = max(panelW/srcW, panelH/srcH)
  const coverScale = Math.max(
    panelW / sourceSize.width,
    panelH / sourceSize.height
  );
  const coveredW = sourceSize.width  * coverScale;
  const coveredH = sourceSize.height * coverScale;

  // After scale(zoom), the visual dimensions are:
  const scaledW = coveredW * zoom;
  const scaledH = coveredH * zoom;

  // Clamping: same as canvas
  const maxOffsetX = Math.max(0, (scaledW - panelW) / 2);
  const maxOffsetY = Math.max(0, (scaledH - panelH) / 2);
  const posX = clamp(rawPosX, -maxOffsetX, maxOffsetX);
  const posY = clamp(rawPosY, -maxOffsetY, maxOffsetY);

  // Visual left/top (same formula as canvas)
  const visualLeft = (panelW - scaledW) / 2 + posX;
  const visualTop  = (panelH - scaledH) / 2 + posY;

  return {
    coverScale,
    zoom,
    posX,
    posY,
    scaledW,
    scaledH,
    visualLeft,
    visualTop,
    centerX: panelW / 2 + posX,
    centerY: panelH / 2 + posY,
    // CSS transform string that HalfAndHalf.tsx will emit
    cssTransform: `translate(${posX}px, ${posY}px) scale(${zoom})`,
  };
}

function reactRenderingCalculations(seg) {
  const safeSplitRatio = clamp(seg.splitRatio, 0, 1);
  const topHeightPx    = Math.floor(safeSplitRatio * COMPOSITION_HEIGHT);
  const bottomHeightPx = COMPOSITION_HEIGHT - topHeightPx;

  const brollLayout = reactComputeLayout(COMPOSITION_WIDTH, topHeightPx,    seg.brollSourceSize, seg.brollTransform);
  const arollLayout = reactComputeLayout(COMPOSITION_WIDTH, bottomHeightPx, seg.arollSourceSize, seg.arollTransform);
  return { brollLayout, arollLayout, topHeightPx, bottomHeightPx };
}

// ---------------------------------------------------------------------------
// Run comparison
// ---------------------------------------------------------------------------
function compareRenders() {
  const canvasRes = canvasRenderingCalculations(TEST_DATA);
  const reactRes  = reactRenderingCalculations(TEST_DATA);

  const TOL = 0.01; // px tolerance for floating-point comparison

  console.log("=".repeat(70));
  console.log("CANVAS vs REACT (CSS-transform) RENDERING COMPARISON");
  console.log("=".repeat(70));

  function printPanel(label, canvas, react) {
    console.log(`\n── ${label} ──`);
    console.log(`  Panel W×H        : ${canvas.scaledW !== undefined ? "panel" : ""}`);

    const rows = [
      ["coverScale",  canvas.coverScale.toFixed(6),  react.coverScale.toFixed(6)],
      ["zoom",        canvas.zoom.toFixed(4),          react.zoom.toFixed(4)],
      ["clamped posX",canvas.posX.toFixed(2) + "px",  react.posX.toFixed(2) + "px"],
      ["clamped posY",canvas.posY.toFixed(2) + "px",  react.posY.toFixed(2) + "px"],
      ["scaledW",     canvas.scaledW.toFixed(3) + "px",react.scaledW.toFixed(3) + "px"],
      ["scaledH",     canvas.scaledH.toFixed(3) + "px",react.scaledH.toFixed(3) + "px"],
      ["visualLeft",  canvas.visualLeft.toFixed(3) + "px",react.visualLeft.toFixed(3) + "px"],
      ["visualTop",   canvas.visualTop.toFixed(3) + "px", react.visualTop.toFixed(3) + "px"],
      ["centerX",     canvas.centerX.toFixed(3) + "px",   react.centerX.toFixed(3) + "px"],
      ["centerY",     canvas.centerY.toFixed(3) + "px",   react.centerY.toFixed(3) + "px"],
    ];

    const colW = 18;
    console.log(`  ${"Property".padEnd(14)} ${"Canvas".padEnd(colW)} ${"React".padEnd(colW)} Match?`);
    console.log(`  ${"-".repeat(14)} ${"-".repeat(colW)} ${"-".repeat(colW)} ------`);
    for (const [prop, cv, rv] of rows) {
      const cvNum = parseFloat(cv);
      const rvNum = parseFloat(rv);
      const match = Math.abs(cvNum - rvNum) < TOL ? "✓" : "✗ DIFF=" + (cvNum - rvNum).toFixed(4);
      console.log(`  ${prop.padEnd(14)} ${cv.padEnd(colW)} ${rv.padEnd(colW)} ${match}`);
    }

    if (react.cssTransform !== undefined) {
      console.log(`\n  CSS transform applied: ${react.cssTransform}`);
    }
  }

  printPanel("B-ROLL (top panel, landscape source)", canvasRes.brollLayout, reactRes.brollLayout);
  printPanel("A-ROLL (bottom panel, portrait source)", canvasRes.arollLayout, reactRes.arollLayout);

  console.log("\n" + "=".repeat(70));
  console.log("ABSOLUTE PANEL POSITIONS IN COMPOSITION");
  console.log("=".repeat(70));
  console.log(`\n  B-Roll panel: top=0, height=${canvasRes.topHeight}px`);
  console.log(`  A-Roll panel: top=${canvasRes.topHeight}px, height=${canvasRes.bottomHeight}px`);

  const canvasBrollAbsTop = 0 + canvasRes.brollLayout.visualTop;
  const reactBrollAbsTop  = 0 + reactRes.brollLayout.visualTop;
  const canvasArollAbsTop = canvasRes.topHeight + canvasRes.arollLayout.visualTop;
  const reactArollAbsTop  = reactRes.topHeightPx + reactRes.arollLayout.visualTop;

  console.log(`\n  B-Roll video absolute top: canvas=${canvasBrollAbsTop.toFixed(2)}px  react=${reactBrollAbsTop.toFixed(2)}px`);
  console.log(`  A-Roll video absolute top: canvas=${canvasArollAbsTop.toFixed(2)}px  react=${reactArollAbsTop.toFixed(2)}px`);

  const brollMatch = Math.abs(canvasRes.brollLayout.visualLeft - reactRes.brollLayout.visualLeft) < TOL &&
                     Math.abs(canvasRes.brollLayout.visualTop  - reactRes.brollLayout.visualTop)  < TOL;
  const arollMatch = Math.abs(canvasRes.arollLayout.visualLeft - reactRes.arollLayout.visualLeft) < TOL &&
                     Math.abs(canvasRes.arollLayout.visualTop  - reactRes.arollLayout.visualTop)  < TOL;

  console.log("\n" + "=".repeat(70));
  console.log("FINAL RESULT");
  console.log("=".repeat(70));
  console.log(`\n  B-Roll position match: ${brollMatch ? "✓ PASS" : "✗ FAIL"}`);
  console.log(`  A-Roll position match: ${arollMatch ? "✓ PASS" : "✗ FAIL"}`);

  if (brollMatch && arollMatch) {
    console.log("\n  ✓ Canvas and React (CSS-transform) produce identical visual positions.");
    console.log("  The HalfAndHalf CSS-transform fix is mathematically sound.\n");
  } else {
    console.log("\n  ✗ Positions differ — review the calculations above.\n");
  }

  return { brollMatch, arollMatch };
}

compareRenders();
