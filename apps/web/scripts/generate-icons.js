#!/usr/bin/env node
/**
 * generate-icons.js — Renders SVG favicons to PNG for PWA / App Store / Play Store.
 *
 * Usage: node scripts/generate-icons.js
 * Requires: npm install resvg-js (or run via npx from the web app directory)
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = resolve(__dirname, "../public");

const SIZES = [
  { name: "icon-192x192.png", size: 192, maskable: false },
  { name: "icon-512x512.png", size: 512, maskable: false },
  { name: "maskable-512x512.png", size: 512, maskable: true },
  { name: "apple-touch-icon.png", size: 180, maskable: false },
];

async function main() {
  let Resvg;
  try {
    const mod = await import("@resvg/resvg-js");
    Resvg = mod.Resvg ?? mod.default?.Resvg;
  } catch {
    console.error(
      "Error: @resvg/resvg-js not found.\n" +
        "Run: cd apps/web && npm install @resvg/resvg-js --save-dev\n" +
        "Then re-run this script."
    );
    process.exit(1);
  }

  const svgTemplate = readFileSync(
    resolve(PUBLIC_DIR, "favicon-512.svg"),
    "utf-8"
  );

  mkdirSync(PUBLIC_DIR, { recursive: true });

  for (const { name, size, maskable } of SIZES) {
    let svg;
    if (maskable) {
      // Maskable icons need 10% safe zone padding
      const pad = Math.round(size * 0.1);
      const inner = size - pad * 2;
      const rx = Math.round(inner * 0.25); // corner radius scaled
      svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
        <rect width="${size}" height="${size}" fill="#006a61"/>
        <defs>
          <linearGradient id="mg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#29a195"/>
            <stop offset="1" stop-color="#006a61"/>
          </linearGradient>
        </defs>
        <rect x="${pad}" y="${pad}" width="${inner}" height="${inner}" rx="${rx}" fill="url(#mg)"/>
        <text x="${size / 2}" y="${size / 2 + inner * 0.35}" font-family="Arial, Helvetica, sans-serif" font-size="${inner * 0.53}" font-weight="700" fill="#ffffff" text-anchor="middle">N</text>
      </svg>`;
    } else {
      // Standard icon: use the template SVG, override width/height
      svg = svgTemplate
        .replace(/width="512"/, `width="${size}"`)
        .replace(/height="512"/, `height="${size}"`)
        .replace(
          /font-size="272"/,
          `font-size="${Math.round(size * 0.53)}"`
        );
    }

    const resvg = new Resvg(svg, {
      fitTo: { mode: "width", value: size },
    });
    const pngData = resvg.render();
    const pngBuffer = pngData.asPng();
    const outPath = resolve(PUBLIC_DIR, name);
    writeFileSync(outPath, pngBuffer);
    console.log(`  ✓ ${name} (${size}x${size}${maskable ? " maskable" : ""})`);
  }

  console.log("\nAll icons generated in public/");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
