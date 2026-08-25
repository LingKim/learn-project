import { defineConfig, devices } from "@playwright/test";

const frontendUrl = "http://127.0.0.1:3100";
const backendUrl = "http://127.0.0.1:8100";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  outputDir: "../output/playwright/test-results",
  reporter: [["list"], ["html", { outputFolder: "../output/playwright/report", open: "never" }]],
  use: {
    baseURL: frontendUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command:
        "cd ../backend && uv run uvicorn xuemian_ai.main:app --host 127.0.0.1 --port 8100 --no-access-log",
      url: `${backendUrl}/api/v1/health/live`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "pnpm dev --hostname 127.0.0.1 --port 3100",
      url: `${frontendUrl}/login`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        BACKEND_INTERNAL_URL: backendUrl,
      },
    },
  ],
});
