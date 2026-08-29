# Design QA — Neutral Dark Mode

- Source visual truth: `C:/Users/ACER/AppData/Local/Temp/codex-clipboard-2769a7e2-e729-4ab3-8595-cdbb08750d2a.png`
- Implementation screenshot: `C:/Users/ACER/AppData/Local/Temp/kerjapedia-neutral-dark-1095x583.png`
- Side-by-side comparison: `C:/Users/ACER/AppData/Local/Temp/kerjapedia-dark-mode-comparison.png`
- Route: `http://localhost:3000/chat`
- Viewport: 1095 × 583 CSS px; mobile regression check at 390 × 844 CSS px
- Pixel dimensions: source 1095 × 583; implementation 1095 × 583
- Density normalization: equal pixel and CSS dimensions; no resampling required
- State: guest chat, dark theme, empty composer

## Full-view comparison evidence

The source exposed the unwanted green cast across the full canvas. The revised implementation uses neutral graphite for the main canvas (`rgb(17, 18, 20)`), near-black neutral chrome for the header/sidebar (`rgb(13, 14, 16)`), and a slightly raised main surface (`rgb(24, 25, 29)`). The hierarchy, typography, content, and composer placement remain intact.

The source image omits the product sidebar while the implementation includes the existing app shell. This is an intentional product constraint and not a regression introduced by the color change.

## Required fidelity surfaces

- Fonts and typography: unchanged; display serif and sans-serif utility hierarchy remain legible in both themes.
- Spacing and layout rhythm: unchanged; desktop grid and mobile stacked cards render without clipping or overlap.
- Colors and visual tokens: passed; green is no longer used as the canvas tint. Neutral surfaces, borders, muted text, and focus accent have distinct semantic roles.
- Image quality and asset fidelity: no raster or illustrative assets are present in this screen; existing icon rendering remains sharp.
- Copy and content: unchanged from the product implementation.

## Focused region comparison

A separate crop was not required because the requested change is global color balance and the composer, suggestion cards, header, and primary canvas are all readable at 1:1 in the full-view comparison.

## Findings

No actionable P0, P1, or P2 findings remain. The only structural difference from the supplied crop is the pre-existing sidebar/app chrome, which was outside the requested color correction.

## Interaction and runtime checks

- Theme interaction: Dark → Light → Dark passed.
- Dark theme restored after the interaction.
- Mobile viewport 390 × 844: meaningful content visible; no framework overlay.
- Browser console: no errors or warnings.
- ESLint: passed.
- TypeScript `--noEmit`: passed.
- Prettier check for `globals.css`: passed.

## Comparison history

1. Initial source/reference comparison identified the green canvas cast as the P1 mismatch.
2. Replaced green-biased dark tokens with neutral graphite tokens and mapped header, sidebar, cards, input, borders, and hover states to semantic dark surfaces.
3. Recaptured at the same 1095 × 583 viewport. The green cast was removed, visual hierarchy remained clear, and no new P0/P1/P2 issues were visible.

final result: passed
