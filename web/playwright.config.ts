import { defineConfig } from "@playwright/test";

export default defineConfig({
  globalSetup: "./demo/global-setup.ts",
  testDir: "./demo",
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
  projects: [
    { name: "web-light", testMatch: "web-demo.ts", use: { colorScheme: "light" } },
    { name: "web-dark", testMatch: "web-demo.ts", use: { colorScheme: "dark" } },
    { name: "dry-light", testMatch: "dry-demo.ts", use: { colorScheme: "light" } },
    { name: "dry-dark", testMatch: "dry-demo.ts", use: { colorScheme: "dark" } },
  ],
});
