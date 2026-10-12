import { defineConfig } from "vitest/config";

export default defineConfig({
  root: "src",
  base: "./",
  build: {
    outDir: "../dist",
    emptyOutDir: true,
    assetsDir: "assets",
    rollupOptions: {
      output: {
        entryFileNames: "assets/main.js",
        assetFileNames: ({ names }) =>
          names.some((name) => name.endsWith(".css"))
            ? "assets/main.css"
            : "assets/[name][extname]",
      },
    },
  },
  test: { environment: "jsdom", root: "." },
});
