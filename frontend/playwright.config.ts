import { defineConfig } from "@playwright/test";
const baseURL = `http://127.0.0.1:${process.env.AQP_TEST_PORT || "8011"}`;
export default defineConfig({
  testDir: "tests",
  workers: 1,
  use: {
    baseURL,
    headless: true,
    ...(process.env.AQP_BROWSER ? { channel: process.env.AQP_BROWSER } : {}),
  },
  webServer: {
    command:
      "..\\.venv\\Scripts\\python.exe ..\\backend\\tests\\browser_server.py",
    url: `${baseURL}/`,
    reuseExistingServer: false,
    timeout: 30000,
  },
});
