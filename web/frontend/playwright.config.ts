import { defineConfig } from "@playwright/test";

/**
 * Runs against this repo's own real `.cdp/index.db` (the default repo
 * selection), not a fixture -- per this project's own convention of
 * verifying against a real index rather than synthetic data. Both servers
 * are started fresh for the run via `webServer` so `npm run test:e2e` is a
 * single command, no manual `uvicorn`/`npm run dev` steps.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: ".venv/bin/uvicorn web.api.app:app --port 8000",
      cwd: "../..",
      port: 8000,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: "npm run dev -- --port 5173",
      port: 5173,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
