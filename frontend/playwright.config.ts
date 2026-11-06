import { defineConfig } from "@playwright/test";

// Uses the locally installed Microsoft Edge (no browser download). Both servers bind
// to 127.0.0.1 only. The backend has no API key and the agent is off: no paid calls.
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5174",
    channel: "msedge",
    headless: true,
  },
  webServer: [
    {
      command: "..\\.venv\\Scripts\\python.exe e2e\\backend.py",
      url: "http://127.0.0.1:8010/health",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npx vite --host 127.0.0.1 --port 5174 --strictPort",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      timeout: 60_000,
      env: { LAB_BACKEND_URL: "http://127.0.0.1:8010" },
    },
  ],
});
