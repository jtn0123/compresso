import { configDefaults, defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'happy-dom',
    globals: true,
    exclude: [...configDefaults.exclude, 'tests/e2e/**', 'tests/e2e-live/**'],
    coverage: {
      provider: 'v8',
      // Track every production source file after the JavaScript-to-TypeScript
      // conversion. Keeping `js` here also makes any regression visible.
      include: ['src/**/*.{js,ts,vue}'],
      exclude: ['src/**/__tests__/**', 'src/test-utils/**'],
      reporter: ['text-summary', 'lcov'],
      reportsDirectory: './coverage',
      thresholds: {
        // Honest all-source baseline (2026-07-12). Ratchet upward as tests are
        // added; never remove files from `include` to satisfy this gate.
        lines: 24,
        functions: 16,
        branches: 17,
        statements: 24,
      },
    },
  },
  resolve: {
    extensions: ['.mjs', '.js', '.ts', '.jsx', '.tsx', '.json', '.vue'],
    alias: {
      '#q-app': path.resolve(__dirname, 'src/test-utils/q-app.ts'),
      src: path.resolve(__dirname, 'src'),
      components: path.resolve(__dirname, 'src/components'),
      layouts: path.resolve(__dirname, 'src/layouts'),
      pages: path.resolve(__dirname, 'src/pages'),
      assets: path.resolve(__dirname, 'src/assets'),
      boot: path.resolve(__dirname, 'src/boot'),
    },
  },
})
