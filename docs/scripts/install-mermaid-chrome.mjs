#!/usr/bin/env node
/**
 * mermaid-cli depends on puppeteer-core, which does NOT download Chrome.
 * This installs the Chrome Headless Shell build Puppeteer expects (one-time, ~150MB).
 *
 * Skip: CI / PUPPETEER_SKIP_BROWSER_DOWNLOAD=1
 */

import { execSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DOCS_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

if (process.env.CI === "true" || process.env.PUPPETEER_SKIP_BROWSER_DOWNLOAD === "1") {
  console.log("[docs] Skipping Chrome install for Mermaid (CI or PUPPETEER_SKIP_BROWSER_DOWNLOAD=1).");
  process.exit(0);
}

try {
  execSync("npx puppeteer browsers install chrome-headless-shell", {
    cwd: DOCS_ROOT,
    stdio: "inherit",
    env: { ...process.env, npm_config_yes: "true" },
    shell: true,
  });
  console.log("[docs] Chrome for Mermaid CLI is ready.");
} catch {
  console.warn(
    "\n[docs] Could not auto-install Chrome for diagram export. When you need PNGs, run:\n" +
      "  cd docs && npm run diagrams:install-browser\n",
  );
  process.exit(0);
}
