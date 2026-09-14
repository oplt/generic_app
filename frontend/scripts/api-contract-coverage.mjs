#!/usr/bin/env node
/**
 * OpenAPI ↔ frontend contract coverage report.
 *
 * Classification (per path+method):
 *   ui_used | programmatic_api_only | health_observability | internal | currently_orphaned
 *
 * Exit 1 only for true contract violations (not intentional API-only orphans).
 *
 * Usage (from frontend/):
 *   node scripts/api-contract-coverage.mjs
 *   node scripts/api-contract-coverage.mjs --check
 */
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(__dirname, "..");
const repoRoot = resolve(frontendRoot, "..");
const openapiPath = join(frontendRoot, "openapi/openapi.json");
const allowlistPath = join(frontendRoot, "openapi/intentional-api-only.json");
const generatedEndpointsDir = join(frontendRoot, "src/generated/endpoints");
const srcRoot = join(frontendRoot, "src");
const reportJsonPath = join(repoRoot, "docs/api-contract-coverage.json");
const reportMdPath = join(repoRoot, "docs/api-contract-coverage.md");

const checkOnly = process.argv.includes("--check");

const TRANSPORT_API_FILES = new Set([
  "client.ts",
  "axiosClient.ts",
  "orvalMutator.ts",
  "developerDiagnosticsEvents.ts",
]);

function walkSrc(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "dist" || entry === "generated") continue;
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) walkSrc(full, out);
    else if (/\.(ts|tsx)$/.test(entry)) out.push(full);
  }
  return out;
}

function walkAll(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "dist") continue;
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) walkAll(full, out);
    else if (/\.(ts|tsx)$/.test(entry)) out.push(full);
  }
  return out;
}

function normalizeTemplate(path) {
  return path
    .replace(/\$\{[^}]+\}/g, "{}")
    .replace(/\{[^}]+\}/g, "{}")
    .replace(/\?.*$/, "")
    .replace(/\/+$/, "") || "/";
}

function opKey(method, path) {
  return `${method.toUpperCase()} ${path}`;
}

function capitalize(name) {
  return name.charAt(0).toUpperCase() + name.slice(1);
}

function extractPathFromUrlFn(text, urlFnName) {
  const re = new RegExp(
    `export const ${urlFnName}\\s*=\\s*[\\s\\S]*?return\\s+(?:[^;\\n]*?[\\\`'"](\\/(?:api\\/v1|health)\\/[^\\\`'"]+)[\\\`'"]|[\\\`'"](\\/(?:api\\/v1|health)\\/[^\\\`'"]+)[\\\`'"])`,
    "m"
  );
  const match = text.match(re);
  if (!match) return null;
  return (match[1] || match[2] || "").split("?")[0];
}

function extractAsyncFns(text) {
  const results = [];
  const re = /export const (\w+) = async\b/g;
  let match;
  while ((match = re.exec(text))) {
    const name = match[1];
    const start = match.index;
    const nextExport = text.indexOf("\nexport ", start + 1);
    const body = text.slice(start, nextExport === -1 ? start + 800 : nextExport);
    const methodMatch = body.match(/method:\s*'([A-Z]+)'/);
    if (!methodMatch) continue;
    results.push({ name, method: methodMatch[1], start });
  }
  return results;
}

function loadOpenApi() {
  const spec = JSON.parse(readFileSync(openapiPath, "utf8"));
  const operations = [];
  for (const [path, methods] of Object.entries(spec.paths || {})) {
    for (const [method, op] of Object.entries(methods)) {
      if (!["get", "post", "put", "patch", "delete"].includes(method)) continue;
      operations.push({
        method: method.toUpperCase(),
        path,
        normalized: normalizeTemplate(path),
        operationId: op.operationId || null,
        tags: op.tags || [],
        summary: op.summary || null,
      });
    }
  }
  return { operations };
}

function parseGeneratedClients() {
  const files = walkAll(generatedEndpointsDir);
  /** @type {Map<string, { file: string, name: string, method: string, pathTemplate: string, normalized: string }>} */
  const byNormalizedMethod = new Map();
  const functionNames = new Set();

  for (const file of files) {
    const text = readFileSync(file, "utf8");
    const rel = relative(frontendRoot, file).replaceAll("\\", "/");
    for (const fn of extractAsyncFns(text)) {
      functionNames.add(fn.name);
      const urlFn = `get${capitalize(fn.name)}Url`;
      const pathTemplate = extractPathFromUrlFn(text, urlFn);
      if (!pathTemplate) continue;
      const normalized = normalizeTemplate(pathTemplate);
      const key = `${fn.method} ${normalized}`;
      byNormalizedMethod.set(key, {
        file: rel,
        name: fn.name,
        method: fn.method,
        pathTemplate,
        normalized,
      });
    }
  }

  return { byNormalizedMethod, functionNames };
}

function loadAllowlist() {
  const raw = JSON.parse(readFileSync(allowlistPath, "utf8"));
  const set = new Set(raw.operations || []);
  return { set, notes: raw.notes || {} };
}

function classifyTag(tags, path) {
  const lower = tags.map((t) => t.toLowerCase());
  if (
    lower.includes("health") ||
    path.startsWith("/health") ||
    path.startsWith("/api/v1/health")
  ) {
    return "health_observability";
  }
  if (
    lower.includes("observability") ||
    lower.includes("developer-diagnostics") ||
    path.includes("/developer/diagnostics")
  ) {
    return "health_observability";
  }
  if (lower.includes("webhook") || /\/webhooks(\/|$)/.test(path)) {
    return "internal";
  }
  return null;
}

function scanFrontendUsage(functionNames) {
  const files = walkSrc(srcRoot);
  const usedFunctions = new Set();
  const staleImports = [];
  const allTextByFile = new Map();

  for (const file of files) {
    const rel = relative(srcRoot, file).replaceAll("\\", "/");
    const text = readFileSync(file, "utf8");
    allTextByFile.set(rel, text);

    for (const m of text.matchAll(
      /import\s*\{([^}]+)\}\s*from\s*["'][^"']*generated\/endpoints[^"']*["']/g
    )) {
      const names = m[1]
        .split(",")
        .map((part) => part.trim().split(/\s+as\s+/).pop().trim())
        .filter(Boolean);
      for (const name of names) {
        if (functionNames.has(name)) {
          usedFunctions.add(name);
          continue;
        }
        if (name.startsWith("use") && /ApiV1/.test(name)) {
          const asyncGuess = name.slice(3, 4).toLowerCase() + name.slice(4);
          if (functionNames.has(asyncGuess)) {
            usedFunctions.add(asyncGuess);
            continue;
          }
        }
        if (/ApiV1/.test(name) && !name.startsWith("use") && !name.startsWith("get")) {
          staleImports.push({ file: rel, name });
        }
      }
    }

    for (const name of functionNames) {
      if (text.includes(name)) usedFunctions.add(name);
    }
  }

  return { usedFunctions, staleImports, allTextByFile };
}

function scanHandwrittenRelativePaths(allTextByFile) {
  /** @type {Set<string>} normalized /api/v1/... templates hit by handwritten clients */
  const normalizedPaths = new Set();
  for (const [rel, text] of allTextByFile) {
    if (!rel.startsWith("api/") || rel.includes(".test.")) continue;
    const base = rel.slice(4);
    if (TRANSPORT_API_FILES.has(base)) continue;
    for (const m of text.matchAll(/["'`](\/[A-Za-z][^"'`?]*)["'`]/g)) {
      let path = m[1];
      if (path.startsWith("//") || path.startsWith("/assets")) continue;
      if (path.startsWith("/health")) {
        normalizedPaths.add(normalizeTemplate(path));
        continue;
      }
      if (!path.startsWith("/api/")) {
        path = `/api/v1${path}`;
      }
      if (path.startsWith("/api/v1/")) {
        normalizedPaths.add(normalizeTemplate(path));
      }
    }
  }
  return normalizedPaths;
}

function classifyWrappers(allTextByFile, functionNames) {
  const wrappers = [];
  for (const [rel, text] of allTextByFile) {
    if (!rel.startsWith("api/") || !rel.endsWith(".ts")) continue;
    if (rel.includes(".test.")) continue;
    const base = rel.slice(4);
    if (TRANSPORT_API_FILES.has(base)) {
      wrappers.push({ file: rel, class: "A_transport" });
      continue;
    }
    const usesGenerated =
      /generated\/endpoints/.test(text) ||
      [...functionNames].some((fn) => text.includes(fn));
    const hasRelativeApiCall = /apiFetch\s*\(\s*["'`]\//.test(text);
    const hasRawPath = /\/api\/v1\//.test(text);
    if (usesGenerated) wrappers.push({ file: rel, class: "B_generated_wrapper" });
    else if (hasRawPath || hasRelativeApiCall)
      wrappers.push({ file: rel, class: "C_duplicate_handwritten" });
    else wrappers.push({ file: rel, class: "D_special_or_event" });
  }
  return wrappers;
}

function buildReport() {
  const { operations } = loadOpenApi();
  const generated = parseGeneratedClients();
  const allowlist = loadAllowlist();
  const usage = scanFrontendUsage(generated.functionNames);
  const wrappers = classifyWrappers(usage.allTextByFile, generated.functionNames);
  const handwrittenPaths = scanHandwrittenRelativePaths(usage.allTextByFile);

  const openapiNormalized = new Map();
  for (const op of operations) {
    openapiNormalized.set(`${op.method} ${op.normalized}`, op);
  }

  const violations = {
    openapi_missing_from_generated: [],
    generated_missing_from_openapi: [],
    stale_generated_imports: usage.staleImports,
  };

  for (const op of operations) {
    const key = `${op.method} ${op.normalized}`;
    if (!generated.byNormalizedMethod.has(key)) {
      violations.openapi_missing_from_generated.push(opKey(op.method, op.path));
    }
  }

  for (const [, gen] of generated.byNormalizedMethod) {
    const key = `${gen.method} ${gen.normalized}`;
    if (!openapiNormalized.has(key)) {
      violations.generated_missing_from_openapi.push(`${gen.method} ${gen.pathTemplate}`);
    }
  }

  const rows = [];
  for (const op of operations) {
    const key = `${op.method} ${op.normalized}`;
    const gen = generated.byNormalizedMethod.get(key);
    const allowKey = opKey(op.method, op.path);
    const tagClass = classifyTag(op.tags, op.path);
    const usedGenerated = gen ? usage.usedFunctions.has(gen.name) : false;
    const usedHandwritten = handwrittenPaths.has(op.normalized);
    const used = usedGenerated || usedHandwritten;

    let classification;
    if (tagClass) classification = tagClass;
    else if (allowlist.set.has(allowKey)) classification = "programmatic_api_only";
    else if (used) classification = "ui_used";
    else classification = "currently_orphaned";

    rows.push({
      method: op.method,
      path: op.path,
      tags: op.tags,
      operation_id: op.operationId,
      generated_function: gen?.name ?? null,
      generated_file: gen?.file ?? null,
      classification,
      usage: usedGenerated ? "generated" : usedHandwritten ? "handwritten_wrapper" : null,
      intentional_note: allowlist.notes[allowKey] ?? null,
    });
  }

  const summary = {
    ui_used: rows.filter((r) => r.classification === "ui_used").length,
    programmatic_api_only: rows.filter((r) => r.classification === "programmatic_api_only")
      .length,
    health_observability: rows.filter((r) => r.classification === "health_observability")
      .length,
    internal: rows.filter((r) => r.classification === "internal").length,
    currently_orphaned: rows.filter((r) => r.classification === "currently_orphaned")
      .length,
  };

  const hasViolations =
    violations.openapi_missing_from_generated.length > 0 ||
    violations.generated_missing_from_openapi.length > 0 ||
    violations.stale_generated_imports.length > 0;

  return {
    version: 1,
    generated_at: new Date().toISOString(),
    openapi_path: "frontend/openapi/openapi.json",
    intentional_api_only: "frontend/openapi/intentional-api-only.json",
    counts: {
      openapi_operations: operations.length,
      generated_operations: generated.byNormalizedMethod.size,
      generated_async_functions: generated.functionNames.size,
      ...summary,
    },
    summary,
    violations,
    wrappers,
    operations: rows,
    orphaned: rows.filter((r) => r.classification === "currently_orphaned"),
    has_contract_violations: hasViolations,
  };
}

function toMarkdown(report) {
  const lines = [
    "# API ↔ frontend contract coverage",
    "",
    `Generated: ${report.generated_at}`,
    "",
    "## Summary",
    "",
    `| Class | Count |`,
    `| --- | ---: |`,
    `| UI-used | ${report.summary.ui_used} |`,
    `| Programmatic / API-only | ${report.summary.programmatic_api_only} |`,
    `| Health / observability | ${report.summary.health_observability} |`,
    `| Internal | ${report.summary.internal} |`,
    `| Currently orphaned | ${report.summary.currently_orphaned} |`,
    `| OpenAPI operations | ${report.counts.openapi_operations} |`,
    "",
    "## Contract violations (CI-failing)",
    "",
  ];

  if (!report.has_contract_violations) {
    lines.push("_None._", "");
  } else {
    for (const [label, items] of [
      ["OpenAPI ops missing from generated SDK", report.violations.openapi_missing_from_generated],
      ["Generated paths missing from OpenAPI", report.violations.generated_missing_from_openapi],
      ["Stale generated imports", report.violations.stale_generated_imports],
    ]) {
      if (!items.length) continue;
      lines.push(`### ${label}`, "");
      for (const item of items) {
        lines.push(
          typeof item === "string" ? `- \`${item}\`` : `- \`${item.file}\` → \`${item.name}\``
        );
      }
      lines.push("");
    }
  }

  lines.push("## Handwritten API modules", "");
  lines.push("| File | Class |", "| --- | --- |");
  for (const w of report.wrappers) {
    lines.push(`| \`${w.file}\` | ${w.class} |`);
  }
  lines.push("");

  if (report.orphaned.length) {
    lines.push("## Currently orphaned (informational)", "");
    lines.push(
      "Present in OpenAPI + SDK but no non-generated frontend caller. Not a CI failure.",
      ""
    );
    for (const row of report.orphaned.slice(0, 100)) {
      lines.push(
        `- \`${row.method} ${row.path}\`${row.generated_function ? ` → \`${row.generated_function}\`` : ""}`
      );
    }
    if (report.orphaned.length > 100) {
      lines.push(`- … +${report.orphaned.length - 100} more`);
    }
    lines.push("");
  }

  lines.push(
    "## How to refresh",
    "",
    "```bash",
    "cd frontend && npm run api:contract",
    "```",
    "",
    "Intentional API-only allow-list: `frontend/openapi/intentional-api-only.json`.",
    "",
    "See also: [frontend-api-contract.md](frontend-api-contract.md).",
    ""
  );
  return lines.join("\n");
}

function main() {
  const report = buildReport();
  mkdirSync(dirname(reportJsonPath), { recursive: true });
  writeFileSync(reportJsonPath, `${JSON.stringify(report, null, 2)}\n`);
  writeFileSync(reportMdPath, toMarkdown(report));

  console.log(
    `Contract coverage: ui=${report.summary.ui_used} api_only=${report.summary.programmatic_api_only} health=${report.summary.health_observability} orphaned=${report.summary.currently_orphaned} violations=${report.has_contract_violations ? "YES" : "no"}`
  );
  console.log(`Wrote ${relative(repoRoot, reportJsonPath)} and ${relative(repoRoot, reportMdPath)}`);

  if (checkOnly && report.has_contract_violations) {
    console.error("Contract violations detected:");
    console.error(JSON.stringify(report.violations, null, 2));
    process.exit(1);
  }
}

main();
