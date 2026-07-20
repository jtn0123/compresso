/*
 * This file runs in a Node context (it's NOT transpiled by Babel), so use only
 * the ES6 features that are supported by your Node version. https://node.green/
 */

// Configuration for your app
// https://v2.quasar.dev/quasar-cli-vite/quasar-config-file

import { fileURLToPath } from 'node:url'

// Load .env variables for devserver proxy configuration
import dotenv from 'dotenv'

import { defineConfig } from '#q-app'

dotenv.config({ quiet: true })

// Root public path — the SPA is always served from under /compresso/*.
// Referenced by build.publicPath and interpolated into index.html (the
// @quasar/app-vite v3 html pipeline no longer prefixes relative href/src
// attributes with the configured publicPath).
const publicPath = '/compresso/'

export default defineConfig(function (ctx) {
  return {
    // https://v2.quasar.dev/quasar-cli-vite/prefetch-feature
    // preFetch: true,

    // app boot file (/src/boot)
    // --> boot files are part of "main.js"
    // https://v2.quasar.dev/quasar-cli-vite/boot-files
    boot: ['i18n', 'axios', 'global-event-bus'],

    // https://v2.quasar.dev/quasar-cli-vite/quasar-config-file#css
    css: ['app.scss', 'admonitions.css'],

    // https://github.com/quasarframework/quasar/tree/dev/extras
    extras: [
      // 'ionicons-v4',
      // 'mdi-v7',
      'fontawesome-v7',
      // 'eva-icons',
      // 'themify',
      // 'line-awesome',
      // 'roboto-font-latin-ext', // this or either 'roboto-font', NEVER both!

      'roboto-font', // optional, you are not bound to it
      'material-icons', // optional, you are not bound to it
      'material-icons-outlined', // optional, you are not bound to it
    ],

    // Full list of options: https://v2.quasar.dev/quasar-cli-vite/quasar-config-file#build
    build: {
      vueRouterMode: 'history', // available values: 'hash', 'history'

      // Set the root public path to /compresso/*
      publicPath,

      // rtl: true, // https://quasar.dev/options/rtl-support
      // preloadChunks: true,
      // showProgress: false,
      // gzip: true,
      // analyze: true,

      // Options below are automatically set depending on the env, set them if you want to override
      // extractCSS: false,

      // Restore the webpack-style aliases that @quasar/app-vite v2 provided by
      // default (v3 only ships "@" and "#q-app"). Keep in sync with vitest.config.js.
      alias: {
        src: fileURLToPath(new URL('./src', import.meta.url)),
        components: fileURLToPath(new URL('./src/components', import.meta.url)),
        layouts: fileURLToPath(new URL('./src/layouts', import.meta.url)),
        pages: fileURLToPath(new URL('./src/pages', import.meta.url)),
        assets: fileURLToPath(new URL('./src/assets', import.meta.url)),
        boot: fileURLToPath(new URL('./src/boot', import.meta.url)),
        stores: fileURLToPath(new URL('./src/stores', import.meta.url)),
      },

      vueOptionsAPI: true,
      extendViteConf(viteConf) {
        viteConf.resolve = viteConf.resolve || {}
        viteConf.resolve.extensions = ['.mjs', '.js', '.ts', '.jsx', '.tsx', '.json', '.vue']
        viteConf.resolve.dedupe = ['vue', 'vue-router', 'quasar']
      },
    },

    // Full list of options: https://v2.quasar.dev/quasar-cli-vite/quasar-config-file#devserver
    devServer: {
      https: false,
      port: 8889,
      proxy: (() => {
        // Allow configuring the backend target via .env
        // Example: COMPRESSO_BACKEND_URL=http://localhost:8888
        const httpTarget = process.env.COMPRESSO_BACKEND_URL || 'http://localhost:8888'

        return {
          '/compresso/api': { target: httpTarget },
          '/compresso/panel': { target: httpTarget },
          '/compresso/swagger': { target: httpTarget },
          '/compresso/websocket': { target: httpTarget, ws: true },
        }
      })(),
      open: false, // opens browser window automatically
    },

    // Variables interpolated into index.html (<%= ... %>)
    htmlVariables: {
      publicPath,
    },

    // https://v2.quasar.dev/quasar-cli-vite/quasar-config-file#framework
    framework: {
      config: {},

      // iconSet: 'material-icons', // Quasar icon set
      // lang: 'en-US', // Quasar language pack

      // For special cases outside of where the auto-import strategy can have an impact
      // (like functional components as one of the examples),
      // you can manually specify Quasar components/directives to be available everywhere:
      //
      // components: [],
      // directives: [],

      // Quasar plugins
      plugins: ['Dialog', 'Notify', 'LocalStorage', 'SessionStorage'],
    },

    // animations: 'all', // --- includes all animations
    // https://quasar.dev/options/animations
    animations: [],

    // https://v2.quasar.dev/quasar-cli-vite/developing-ssr/configuring-ssr
    ssr: {
      pwa: false,

      // manualStoreHydration: true,
      // manualPostHydrationTrigger: true,

      prodPort: 3000, // The default port that the production server should use
      // (gets superseded if process.env.PORT is specified at runtime)

      maxAge: 1000 * 60 * 60 * 24 * 30,
      // Tell browser when a file from the server should expire from cache (in ms)

      middlewares: [
        ctx.prod ? 'compression' : '',
        'render', // keep this as last one
      ],
    },

    // https://v2.quasar.dev/quasar-cli-vite/developing-pwa/configuring-pwa
    pwa: {
      workboxPluginMode: 'GenerateSW', // 'GenerateSW' or 'InjectManifest'
      workboxOptions: {}, // only for GenerateSW

      manifest: {
        name: `Compresso`,
        short_name: `Compresso`,
        description: `Media library optimizer with approval workflow and compression dashboard`,
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#f8faf9',
        theme_color: '#1a6b4a',
        icons: [
          {
            src: 'icons/icon-128x128.png',
            sizes: '128x128',
            type: 'image/png',
          },
          {
            src: 'icons/icon-192x192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: 'icons/icon-256x256.png',
            sizes: '256x256',
            type: 'image/png',
          },
          {
            src: 'icons/icon-384x384.png',
            sizes: '384x384',
            type: 'image/png',
          },
          {
            src: 'icons/icon-512x512.png',
            sizes: '512x512',
            type: 'image/png',
          },
        ],
      },
    },

    // Full list of options: https://v2.quasar.dev/quasar-cli-vite/developing-cordova-apps/configuring-cordova
    cordova: {
      // noIosLegacyBuildFlag: true, // uncomment only if you know what you are doing
    },

    // Full list of options: https://v2.quasar.dev/quasar-cli-vite/developing-capacitor-apps/configuring-capacitor
    capacitor: {
      hideSplashscreen: true,
    },

    // Full list of options: https://v2.quasar.dev/quasar-cli-vite/developing-electron-apps/configuring-electron
    electron: {
      bundler: 'packager', // 'packager' or 'builder'

      packager: {
        // https://github.com/electron-userland/electron-packager/blob/master/docs/api.md#options
        // OS X / Mac App Store
        // appBundleId: '',
        // appCategoryType: '',
        // osxSign: '',
        // protocol: 'myapp://path',
        // Windows only
        // win32metadata: { ... }
      },

      builder: {
        // https://www.electron.build/configuration/configuration

        appId: 'compresso-frontend',
      },
    },
  }
})
