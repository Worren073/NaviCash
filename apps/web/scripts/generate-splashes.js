#!/usr/bin/env node
/**
 * generate-splashes.js — Generates Apple splash screen PNGs for NaviCash.
 *
 * Usage: node scripts/generate-splashes.js
 * Requires: @resvg/resvg-js (already in devDependencies)
 */
import { writeFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = resolve(__dirname, "../public");

// Key iPhone splash screen resolutions
const SPLASHES = [
  { name: "splash-640x1136.png", w: 640, h: 1136 },   // iPhone SE (1st gen)
  { name: "splash-750x1334.png", w: 750, h: 1334 },   // iPhone 6/7/8
  { name: "splash-1242x2208.png", w: 1242, h: 2208 }, // iPhone 6+/7+/8+
  { name: "splash-1125x2436.png", w: 1125, h: 2436 }, // iPhone X/XS/11 Pro
  { name: "splash-1284x2778.png", w: 1284, h: 2778 }, // iPhone 12/13 Pro Max, 14 Plus
  { name: "splash-1290x2796.png", w: 1290, h: 2796 }, // iPhone 14 Pro Max, 15/16 Pro Max
];

function makeSplashSVG(w, h) {
  const logoSize = Math.round(Math.min(w, h) * 0.22);
  const rx = Math.round(logoSize * 0.25);
  const fontSize = Math.round(logoSize * 0.53);
  const subSize = Math.round(w * 0.038);

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#29a195"/>
      <stop offset="1" stop-color="#006a61"/>
    </linearGradient>
  </defs>
  <rect width="${w}" height="${h}" fill="url(#bg)"/>
  <!-- Logo -->
  <rect x="${(w - logoSize) / 2}" y="${h * 0.35}" width="${logoSize}" height="${logoSize}" rx="${rx}" fill="rgba(255,255,255,0.15)"/>
  <text x="${w / 2}" y="${h * 0.35 + logoSize * 0.72}" font-family="Arial, Helvetica, sans-serif" font-size="${fontSize}" font-weight="700" fill="#ffffff" text-anchor="middle">N</text>
  <!-- App name -->
  <text x="${w / 2}" y="${h * 0.35 + logoSize + subSize * 2.5}" font-family="Arial, Helvetica, sans-serif" font-size="${subSize}" font-weight="600" fill="rgba(255,255,255,0.9)" text-anchor="middle">NaviCash</text>
</svg>`;
}

async function main() {
  let Resvg;
  try {
    const mod = await import("@resvg/resvg-js");
    Resvg = mod.Resvg ?? mod.default?.Resvg;
  } catch {
    console.error("Error: @resvg/resvg-js not found.");
    process.exit(1);
  }

  mkdirSync(PUBLIC_DIR, { recursive: true });

  for (const { name, w, h } of SPLASHES) {
    const svg = makeSplashSVG(w, h);
    const resvg = new Resvg(svg, { fitTo: { mode: "width", value: w } });
    const pngData = resvg.render();
    const pngBuffer = pngData.asPng();
    writeFileSync(resolve(PUBLIC_DIR, name), pngBuffer);
    console.log(`  ✓ ${name} (${w}×${h})`);
  }

  console.log("\nAll splash screens generated in public/");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
