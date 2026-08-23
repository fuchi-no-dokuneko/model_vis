import { mkdirSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const reports = [
  ["test/ui/data-store.test.mjs", "coverage/data-store.lcov"],
  ["test/ui/graph-model.test.mjs", "coverage/graph-model.lcov"],
];

mkdirSync("coverage", { recursive: true });
for (const [testFile, report] of reports) {
  const result = spawnSync(process.execPath, [
    "--experimental-test-coverage",
    "--test-reporter=lcov",
    "--test",
    testFile,
  ], { encoding: "utf8" });
  if (result.stderr) process.stderr.write(result.stderr);
  if (result.status !== 0) process.exit(result.status ?? 1);
  writeFileSync(report, result.stdout, "utf8");
}
