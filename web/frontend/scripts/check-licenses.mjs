#!/usr/bin/env node
// Licence gate for `web/frontend`'s npm dependency tree (`PLAN.md` Phase 5,
// `WEB_RESEARCH.md` §6.4). Walks actually-installed `node_modules/**/package.json`
// files directly rather than `npm ls --json`: that command also lists
// undownloaded optional platform binaries (declared `optionalDependencies` for
// OSes/archs other than the CI runner's) with no license metadata at all,
// which reads as a false failure. Reading installed packages on disk only
// reports what's really shipped in this build.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;

// Permissive licences only. MPL-2.0 (lightningcss, a build-time-only CSS
// compiler behind `@tailwindcss/vite` -- never bundled into shipped app code)
// and 0BSD (tslib) are allowed alongside the original MIT/Apache-2.0/BSD/ISC
// set -- a deliberate call, not an oversight: see the licence-gate decision
// in this cycle's conversation. Python-2.0 (argparse, pulled in transitively
// by `@cdp/web-client`'s `openapi-typescript` codegen devDependency, never
// part of the shipped app bundle) is OSI-approved and permissive in the same
// spirit as BSD -- allowed too.
const ALLOWED = new Set([
  "MIT",
  "Apache-2.0",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "0BSD",
  "ISC",
  "MPL-2.0",
  "Python-2.0",
]);

function findPackages(root) {
  const nodeModules = join(root, "node_modules");
  const out = [];
  if (!existsSync(nodeModules)) return out;
  (function walk(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith(".")) continue;
      const full = join(dir, entry.name);
      if (entry.name.startsWith("@")) {
        if (entry.isDirectory()) walk(full);
        continue;
      }
      if (!entry.isDirectory() && !entry.isSymbolicLink()) continue;
      const pkgJsonPath = join(full, "package.json");
      if (existsSync(pkgJsonPath)) out.push(pkgJsonPath);
      const nested = join(full, "node_modules");
      if (existsSync(nested)) walk(nested);
    }
  })(nodeModules);
  return out;
}

function licenceOf(pkg) {
  if (typeof pkg.license === "string") return pkg.license;
  if (Array.isArray(pkg.licenses)) return pkg.licenses.map((l) => l.type).join(" OR ");
  return null;
}

// SPDX dual-licence expressions ("(MIT OR CC0-1.0)", "MIT OR Apache-2.0")
// pass if any one alternative is allowed -- the consumer can pick that one.
function isAllowed(licence) {
  const alternatives = licence
    .replace(/^\(|\)$/g, "")
    .split(/\s+OR\s+/i)
    .map((s) => s.trim());
  return alternatives.some((alt) => ALLOWED.has(alt));
}

const violations = [];
const unknown = [];
let checked = 0;

for (const pkgJsonPath of findPackages(ROOT)) {
  let pkg;
  try {
    pkg = JSON.parse(readFileSync(pkgJsonPath, "utf8"));
  } catch {
    continue;
  }
  if (pkg.private) continue; // first-party workspace packages (e.g. @cdp/web-client), not a third-party dep
  checked += 1;
  const licence = licenceOf(pkg);
  const id = `${pkg.name}@${pkg.version}`;
  if (licence === null) {
    unknown.push(id);
  } else if (!isAllowed(licence)) {
    violations.push(`${id}: ${licence}`);
  }
}

console.log(`checked ${checked} installed package(s), allowlist: ${[...ALLOWED].join(", ")}`);

if (unknown.length) {
  console.log(`\n${unknown.length} package(s) with no license field (not failing on these, review manually):`);
  for (const id of unknown) console.log(`  - ${id}`);
}

if (violations.length) {
  console.error(`\n${violations.length} package(s) outside the licence allowlist:`);
  for (const v of violations) console.error(`  - ${v}`);
  process.exit(1);
}

console.log("\nall installed licences allowed.");
