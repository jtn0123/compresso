// ESLint flat config (ESLint 9+).
// Replaces the legacy .eslintrc.js / .eslintignore pair.

import pluginVue from 'eslint-plugin-vue'
import prettier from 'eslint-config-prettier/flat'
import babelParser from '@babel/eslint-parser'
import globals from 'globals'
import tseslint from 'typescript-eslint'
import vueParser from 'vue-eslint-parser'

// Globals previously declared via `env.browser` plus the explicit list in
// the old .eslintrc.js.
const projectGlobals = {
  ...globals.browser,
  ga: 'readonly', // Google Analytics
  cordova: 'readonly',
  __statics: 'readonly',
  __QUASAR_SSR__: 'readonly',
  __QUASAR_SSR_SERVER__: 'readonly',
  __QUASAR_SSR_CLIENT__: 'readonly',
  __QUASAR_SSR_PWA__: 'readonly',
  process: 'readonly',
  Capacitor: 'readonly',
  chrome: 'readonly',
}

export default [
  // Replaces the old .eslintignore file.
  {
    ignores: [
      'dist/**',
      'coverage/**',
      'playwright-report/**',
      'src-bex/www/**',
      'src-capacitor/**',
      'src-cordova/**',
      '.quasar/**',
      'node_modules/**',
      'test-results/**',
      'src/types/generated/api.ts',
      '**/*.cjs',
      'quasar.config.*.temporary.compiled*',
      'eslint.config.mjs',
    ],
  },

  // Priority B: Strongly Recommended (was 'plugin:vue/vue3-strongly-recommended').
  ...pluginVue.configs['flat/strongly-recommended'],
  ...tseslint.configs.recommended,

  // Disables formatting rules that conflict with Prettier.
  prettier,

  {
    files: ['**/*.js', '**/*.ts', '**/*.vue'],
    languageOptions: {
      ecmaVersion: 2021,
      sourceType: 'module',
      globals: projectGlobals,
    },
    rules: {
      'prefer-promise-reject-errors': 'off',
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
          destructuredArrayIgnorePattern: '^_',
          varsIgnorePattern: '^_',
        },
      ],
      // Allow debugger during development only.
      'no-debugger': process.env.NODE_ENV === 'production' ? 'error' : 'off',
    },
  },

  {
    files: ['**/*.ts'],
    languageOptions: {
      parser: tseslint.parser,
    },
  },

  // Plain JS files: parse with @babel/eslint-parser (matches legacy config).
  {
    files: ['**/*.js'],
    languageOptions: {
      parser: babelParser,
      parserOptions: {
        requireConfigFile: false,
        babelOptions: {
          babelrc: false,
          configFile: false,
        },
      },
    },
  },

  // Node-context config files (not transpiled by Babel).
  {
    files: ['quasar.config.js', 'vitest.config.js', 'playwright.config.js', 'playwright.live.config.js'],
    languageOptions: {
      globals: globals.node,
    },
  },

  // Vue SFCs keep vue-eslint-parser as the file parser; TypeScript script
  // blocks are parsed by typescript-eslint.
  {
    files: ['**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },
]
