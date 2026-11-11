import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "tests",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8011",
    headless: true,
    ...(process.env.AQP_BROWSER ? { channel: process.env.AQP_BROWSER } : {}),
  },
  webServer: {
    command:
      "..\\.venv\\Scripts\\python.exe ..\\backend\\tests\\browser_server.py",
    url: "http://127.0.0.1:8011/",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
