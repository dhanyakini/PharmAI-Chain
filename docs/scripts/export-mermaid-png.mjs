#!/usr/bin/env node
/**
 * Extracts ```mermaid blocks from docs/FLOWCHARTS.md and renders each to PNG.
 * Filenames come from the nearest preceding `##` heading (slugified), e.g.
 *   system-context.png, authentication-flow.png, authentication-flow-2.png
 *
 * Usage: cd docs && npm install && npm run diagrams:png
 */

import { readFileSync, mkdirSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DOCS_ROOT = join(__dirname, "..");
const MD_FILE = join(DOCS_ROOT, "FLOWCHARTS.md");
const CONFIG_FILE = join(DOCS_ROOT, "mermaid-config.json");
const OUT_PNG = join(DOCS_ROOT, "diagrams", "png");
const OUT_BUILD = join(DOCS_ROOT, "diagrams", "build");

const WIDTH = process.env.MERMAID_WIDTH || "2400";
const HEIGHT = process.env.MERMAID_HEIGHT || "1800";
const BG = process.env.MERMAID_BG || "white";

/** Turn a `##` heading line into a safe filename stem. */
function slugifyHeading(headingLine) {
  let t = headingLine.replace(/^##\s+/, "").trim();
  t = t.replace(/^\d+\.\s*/, "");
  t = t.replace(/\s*\([^)]*\)\s*/g, " ").trim();
  t = t.replace(/&/g, "and");
  const slug = t
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return slug || "diagram";
}

/**
 * Walk markdown: track latest ## slug; each ```mermaid block gets
 * `slug.png` or `slug-2.png` if multiple under the same section.
 */
function parseMermaidBlocks(markdown) {
  const lines = markdown.split("\n");
  /** @type {{ slug: string; body: string }[]} */
  const blocks = [];
  let sectionSlug = "diagram";
  const countPerSection = new Map();
  const usedNames = new Set();

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith("## ") && !line.startsWith("###")) {
      sectionSlug = slugifyHeading(line);
      continue;
    }

    if (line.trim() !== "```mermaid") continue;

    const bodyLines = [];
    i++;
    while (i < lines.length && lines[i].trim() !== "```") {
      bodyLines.push(lines[i]);
      i++;
    }
    const body = bodyLines.join("\n").trim();
    if (!body) continue;

    const n = (countPerSection.get(sectionSlug) ?? 0) + 1;
    countPerSection.set(sectionSlug, n);
    let base = n === 1 ? sectionSlug : `${sectionSlug}-${n}`;

    let slug = base;
    let bump = n;
    while (usedNames.has(slug)) {
      bump++;
      slug = `${sectionSlug}-${bump}`;
    }
    usedNames.add(slug);

    blocks.push({ slug, body });
  }

  return blocks;
}

function main() {
  if (!existsSync(MD_FILE)) {
    console.error("Missing:", MD_FILE);
    process.exit(1);
  }
  if (!existsSync(CONFIG_FILE)) {
    console.error("Missing:", CONFIG_FILE);
    process.exit(1);
  }

  const md = readFileSync(MD_FILE, "utf8");
  const blocks = parseMermaidBlocks(md);

  if (blocks.length === 0) {
    console.error("No ```mermaid blocks found in FLOWCHARTS.md");
    process.exit(1);
  }

  mkdirSync(OUT_PNG, { recursive: true });
  mkdirSync(OUT_BUILD, { recursive: true });

  const mmdc = join(DOCS_ROOT, "node_modules", ".bin", "mmdc");
  if (!existsSync(mmdc)) {
    console.error(
      "mmdc not found. Run:  cd docs && npm install\n" +
        "(installs @mermaid-js/mermaid-cli and Chromium for Puppeteer)",
    );
    process.exit(1);
  }

  console.log(`Rendering ${blocks.length} diagram(s) → ${OUT_PNG}\n`);

  for (const { slug, body } of blocks) {
    const mmdPath = join(OUT_BUILD, `${slug}.mmd`);
    const pngPath = join(OUT_PNG, `${slug}.png`);

    writeFileSync(mmdPath, body, "utf8");

    const args = ["-i", mmdPath, "-o", pngPath, "-c", CONFIG_FILE, "-w", WIDTH, "-H", HEIGHT, "-b", BG];

    try {
      execFileSync(mmdc, args, { cwd: DOCS_ROOT, stdio: "inherit" });
      console.log(`  ✓ ${slug}.png`);
    } catch {
      console.error(`  ✗ failed: ${slug}`);
      console.error(
        "\nIf the error mentions Chrome / Chromium, install the browser for Puppeteer:\n" +
          "  cd docs && npm run diagrams:install-browser\n" +
          "Then run: npm run diagrams:png\n",
      );
      process.exit(1);
    }
  }

  console.log("\nDone. PNG files:", OUT_PNG);
}

main();
