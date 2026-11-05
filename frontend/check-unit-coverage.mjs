import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const output = resolve(root, ".local-dev");
mkdirSync(output, { recursive: true });
const result = spawnSync(
  process.execPath,
  [
    resolve(root, "node_modules/vitest/vitest.mjs"),
    "run",
    "--coverage",
    "--reporter=default",
    "--reporter=json",
    "--outputFile=.local-dev/unit-tests.json",
  ],
  { cwd: root, stdio: "inherit" },
);

// Inventory every application source, including files that no test happens to import.
function sources(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory()
      ? sources(resolve(directory, entry.name))
      : /\.(ts|tsx)$/.test(entry.name)
        ? [resolve(directory, entry.name)]
        : [],
  );
}

let summary = { status: "fail" };
try {
  const tests = JSON.parse(
    readFileSync(resolve(output, "unit-tests.json"), "utf8"),
  );
  const report = JSON.parse(
    readFileSync(resolve(output, "coverage/coverage-summary.json"), "utf8"),
  );
  const expected = sources(resolve(root, "src")).sort();
  const found = Object.keys(report)
    .filter((key) => key !== "total")
    .sort();
  if (JSON.stringify(expected) !== JSON.stringify(found))
    throw new Error("Incomplete source inventory");
  let total = 0,
    covered = 0;
  for (const file of expected) {
    const lines = report[file].lines;
    if (
      ![lines.total, lines.covered, lines.skipped].every(Number.isInteger) ||
      lines.skipped !== 0 ||
      lines.covered < 0 ||
      lines.covered > lines.total
    )
      throw new Error("Invalid raw counts");
    total += lines.total;
    covered += lines.covered;
  }
  const failures =
    tests.numFailedTests + tests.numPendingTests + (tests.numTodoTests ?? 0);
  const pass =
    result.status === 0 &&
    tests.numTotalTests > 0 &&
    failures === 0 &&
    total > 0 &&
    covered * 100 >= total * 95 &&
    report.total.lines.total === total &&
    report.total.lines.covered === covered;
  summary = {
    status: pass ? "pass" : "fail",
    tests: tests.numTotalTests,
    failures,
    covered,
    total,
    source_files: expected.length,
    required_line_percent: 95,
    unit_only: true,
  };
} catch {
  // Missing/stale/invalid evidence cannot turn a failed test run into a successful gate.
  summary = { status: "fail", error: "Missing or invalid unit-only evidence" };
}
writeFileSync(
  resolve(output, "unit-summary.json"),
  JSON.stringify(summary, null, 2) + "\n",
);
console.log(JSON.stringify(summary));
process.exit(summary.status === "pass" ? 0 : 1);
