// ESLint flat config (ESLint 9+).
// Replaces the legacy .eslintrc.js / .eslintignore pair.

import pluginVue from 'eslint-plugin-vue'
import prettier from 'eslint-config-prettier/flat'
import babelParser from '@babel/eslint-parser'
import globals from 'globals'

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
      'src-bex/www/**',
      'src-capacitor/**',
      'src-cordova/**',
      '.quasar/**',
      'node_modules/**',
      '**/*.cjs',
      'babel.config.js',
      'quasar.config.*.temporary.compiled*',
      'eslint.config.mjs',
    ],
  },

  // Priority B: Strongly Recommended (was 'plugin:vue/vue3-strongly-recommended').
  ...pluginVue.configs['flat/strongly-recommended'],

  // Disables formatting rules that conflict with Prettier.
  prettier,

  {
    files: ['**/*.js', '**/*.vue'],
    languageOptions: {
      ecmaVersion: 2021,
      sourceType: 'module',
      globals: projectGlobals,
    },
    rules: {
      'prefer-promise-reject-errors': 'off',
      // Allow debugger during development only.
      'no-debugger': process.env.NODE_ENV === 'production' ? 'error' : 'off',
    },
  },

  // Plain JS files: parse with @babel/eslint-parser (matches legacy config).
  {
    files: ['**/*.js'],
    languageOptions: {
      parser: babelParser,
      parserOptions: { requireConfigFile: false },
    },
  },

  // Vue SFCs keep vue-eslint-parser as the file parser; <script> blocks are
  // parsed by @babel/eslint-parser.
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: { parser: babelParser, requireConfigFile: false },
    },
  },
]
