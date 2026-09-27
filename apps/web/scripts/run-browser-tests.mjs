import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { spawn, spawnSync } from "node:child_process";

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const directory = join(projectRoot, "tests");
const productionDist = ".next-integration-build";
const files = readdirSync(directory).filter((name) => name.endsWith("-browser.cjs")).sort();
const base = "http://127.0.0.1:3100";
let server;

(async () => {
  try {
    if (!existsSync(join(projectRoot, productionDist, "BUILD_ID"))) {
      const build = spawnSync(process.execPath, ["node_modules/next/dist/bin/next", "build", "--webpack"], {
        cwd: projectRoot,
        stdio: "inherit",
        env: { ...process.env, NEXT_DIST_DIR: productionDist },
      });
      if (build.error) throw build.error;
      if (build.status !== 0) throw new Error("Integration production build failed.");
    }
    server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "dev", "--hostname", "127.0.0.1", "--port", "3100"], {
      cwd: projectRoot,
      stdio: "inherit",
      env: { ...process.env, NEXT_DIST_DIR: ".next-integration-dev" },
    });
    let ready = false;
    for (let attempt = 0; attempt < 120; attempt++) {
      if (server.exitCode !== null) throw new Error("Integration web server exited.");
      try {
        ready = (await fetch(base + "/chat")).ok;
      } catch {}
      if (ready) break;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    if (!ready) throw new Error("Integration web server did not start.");
    for (const name of files) {
      const result = spawnSync(process.execPath, [join(directory, name)], {
        stdio: "inherit",
        env: { ...process.env, PLAYWRIGHT_BASE_URL: base, TEST_NEXT_DIST_DIR: productionDist },
      });
      if (result.error) throw result.error;
      if (result.status !== 0) {
        process.exitCode = result.status || 1;
        break;
      }
    }
  } catch (error) {
    console.error(error);
    process.exitCode = 1;
  } finally {
    server?.kill();
  }
})();
