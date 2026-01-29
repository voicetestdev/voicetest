import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./demo",
  testMatch: "web-demo.ts",
  timeout: 60000,
  use: {
    baseURL: "http://localhost:8000",
    video: {
      mode: "on",
      size: { width: 1280, height: 720 },
    },
    launchOptions: {
      slowMo: 100,
    },
  },
  outputDir: "../docs/demos/test-results",
});
