import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      thresholds: {
        perFile: true,
        autoUpdate: true,
        branches: 90,
        functions: 100,
        lines: 100,
        statements: 97.87,
      },
    },
  },
});
