#!/usr/bin/env node
/**
 * Compare Vite/PWA build outputs against baseline-derived budgets.
 *
 * Usage (from frontend/): node scripts/check-budgets.mjs
 * Expects `npm run build` to have produced dist/.
 */
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const distDir = join(root, "dist");
const assetsDir = join(distDir, "assets");
const budgetsPath = join(root, "budgets.json");
const reportPath = join(root, "budget-report.json");

function formatKiB(bytes) {
  return `${(bytes / 1024).toFixed(2)} KiB`;
}

function loadBudgets() {
  return JSON.parse(readFileSync(budgetsPath, "utf8"));
}

function assetSize(match) {
  const pattern = new RegExp(match);
  const matches = readdirSync(assetsDir).filter((name) => pattern.test(name));
  if (matches.length === 0) {
    throw new Error(`No dist/assets file matched ${match}`);
  }
  if (matches.length > 1) {
    throw new Error(`Ambiguous matches for ${match}: ${matches.join(", ")}`);
  }
  const file = matches[0];
  return { file: `assets/${file}`, bytes: statSync(join(assetsDir, file)).size };
}

function precacheEntries() {
  const swPath = join(distDir, "sw.js");
  const source = readFileSync(swPath, "utf8");
  const start = source.indexOf("precacheAndRoute([");
  if (start < 0) {
    throw new Error("Could not find precacheAndRoute([ in dist/sw.js");
  }
  const fromArray = source.slice(start + "precacheAndRoute(".length);
  const end = fromArray.indexOf("],");
  if (end < 0) {
    throw new Error("Could not find end of precache manifest in dist/sw.js");
  }
  const manifestSource = fromArray.slice(0, end + 1);
  const urls = [...manifestSource.matchAll(/url:"([^"]+)"/g)].map((match) => match[1]);
  if (urls.length === 0) {
    throw new Error("No precache urls found in dist/sw.js");
  }
  return urls.map((url) => {
    const rel = url.replace(/^\//, "");
    const full = join(distDir, rel);
    return { url: rel, bytes: statSync(full).size };
  });
}

function evaluate(budget, measured) {
  const { bytes, file, files } = measured;
  let status = "ok";
  if (bytes > budget.maxBytes) status = "fail";
  else if (bytes > budget.warnBytes) status = "warn";
  return {
    id: budget.id,
    label: budget.label,
    kind: budget.kind,
    file: file ?? null,
    files: files ?? null,
    bytes,
    baselineBytes: budget.baselineBytes,
    warnBytes: budget.warnBytes,
    maxBytes: budget.maxBytes,
    deltaBytes: bytes - budget.baselineBytes,
    deltaPercent: Number(
      (((bytes - budget.baselineBytes) / budget.baselineBytes) * 100).toFixed(2)
    ),
    status,
  };
}

function main() {
  const config = loadBudgets();
  const results = [];

  for (const budget of config.budgets) {
    if (budget.kind === "asset") {
      results.push(evaluate(budget, assetSize(budget.match)));
      continue;
    }
    if (budget.kind === "precache") {
      const entries = precacheEntries();
      const bytes = entries.reduce((sum, entry) => sum + entry.bytes, 0);
      results.push(
        evaluate(budget, {
          bytes,
          files: entries.map((entry) => `${entry.url} (${formatKiB(entry.bytes)})`),
        })
      );
      continue;
    }
    throw new Error(`Unknown budget kind: ${budget.kind}`);
  }

  const report = {
    generatedAt: new Date().toISOString(),
    budgetsVersion: config.version,
    results,
    summary: {
      ok: results.filter((item) => item.status === "ok").length,
      warn: results.filter((item) => item.status === "warn").length,
      fail: results.filter((item) => item.status === "fail").length,
    },
  };
  writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");

  console.log("Frontend bundle / PWA budget report");
  console.log("===================================");
  for (const item of results) {
    const marker =
      item.status === "fail" ? "FAIL" : item.status === "warn" ? "WARN" : "OK  ";
    const where = item.file ? ` (${item.file})` : "";
    console.log(
      `[${marker}] ${item.id}${where}: ${formatKiB(item.bytes)} ` +
        `(baseline ${formatKiB(item.baselineBytes)}, ` +
        `Δ ${item.deltaPercent >= 0 ? "+" : ""}${item.deltaPercent}%, ` +
        `warn ${formatKiB(item.warnBytes)}, max ${formatKiB(item.maxBytes)})`
    );
  }
  console.log(`Wrote ${reportPath}`);

  if (report.summary.fail > 0) {
    console.error(
      `\n${report.summary.fail} budget(s) exceeded maxBytes. ` +
        "Investigate growth or intentionally raise baselines in budgets.json."
    );
    process.exit(1);
  }
  if (report.summary.warn > 0) {
    console.warn(
      `\n${report.summary.warn} budget(s) exceeded warnBytes but stayed under maxBytes.`
    );
  }
}

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
}
