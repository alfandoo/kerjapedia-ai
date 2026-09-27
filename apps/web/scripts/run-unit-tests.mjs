import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const directory = join(dirname(fileURLToPath(import.meta.url)), "..", "tests");
const files = readdirSync(directory)
  .filter((name) => name.endsWith(".test.cjs"))
  .map((name) => join(directory, name))
  .sort();
const result = spawnSync(process.execPath, ["--test", ...files], {
  stdio: "inherit",
  env: process.env,
});
if (result.error) throw result.error;
process.exit(result.status || 0);
