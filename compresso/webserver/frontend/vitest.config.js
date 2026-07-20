import { configDefaults, defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import coverageThresholds from './coverage-thresholds.json'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'happy-dom',
    globals: true,
    exclude: [...configDefaults.exclude, 'tests/e2e/**', 'tests/e2e-live/**'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{js,vue}'],
      exclude: ['src/**/__tests__/**', 'src/test-utils/**'],
      // json-summary feeds scripts/check-coverage-ratchet.mjs
      reporter: ['text-summary', 'lcov', 'json-summary'],
      reportsDirectory: './coverage',
      thresholds: {
        // Floors live in coverage-thresholds.json, shared with the auto-
        // ratchet check (scripts/check-coverage-ratchet.mjs) which fails CI
        // when achieved coverage outgrows a floor - so the floors must be
        // raised as tests are added. Never remove files from `include` to
        // satisfy this gate.
        lines: coverageThresholds.lines,
        functions: coverageThresholds.functions,
        branches: coverageThresholds.branches,
        statements: coverageThresholds.statements,
      },
    },
  },
  resolve: {
    extensions: ['.mjs', '.js', '.ts', '.jsx', '.tsx', '.json', '.vue'],
    alias: {
      src: path.resolve(__dirname, 'src'),
      components: path.resolve(__dirname, 'src/components'),
      layouts: path.resolve(__dirname, 'src/layouts'),
      pages: path.resolve(__dirname, 'src/pages'),
      assets: path.resolve(__dirname, 'src/assets'),
      boot: path.resolve(__dirname, 'src/boot'),
    },
  },
})
