import { mount, shallowMount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

// Minimal i18n for tests - returns the key as the translation
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en: {} },
  missing: (_locale, key) => key,
});

// Minimal $q mock to satisfy components that call useQuasar()
const quasarMock = {
  notify: () => {},
  dialog: () => ({ onOk: () => ({ onCancel: () => ({}) }) }),
  dark: { isActive: false },
  screen: {
    gt: { xs: true, sm: true, md: true, lg: true },
    lt: { sm: false, md: false, lg: false, xl: false },
    xs: false, sm: false, md: true, lg: false, xl: false,
    width: 1024,
    height: 768,
  },
  platform: { is: { desktop: true, mobile: false } },
  localStorage: { getItem: () => null, setItem: () => {}, has: () => false },
};

/**
 * Mount a component with i18n and a lightweight Quasar-like $q mock.
 * The real Quasar plugin is not installed because its SSR build
 * does not work in the happy-dom test environment.
 */
export function mountWithQuasar(component, options = {}) {
  const globalOpts = options.global || {};
  return mount(component, {
    ...options,
    global: {
      plugins: [i18n, ...(globalOpts.plugins || [])],
      mocks: {
        $q: quasarMock,
        ...(globalOpts.mocks || {}),
      },
      stubs: {
        teleport: true,
        // Stub all q-* elements so we don't need the real Quasar components
        'q-page': { template: '<div class="q-page"><slot /></div>' },
        'q-card': { template: '<div class="q-card"><slot /></div>' },
        'q-card-section': { template: '<div class="q-card-section"><slot /></div>' },
        'q-card-actions': { template: '<div class="q-card-actions"><slot /></div>' },
        'q-btn': { template: '<button class="q-btn"><slot /></button>', props: ['disable', 'loading', 'color', 'icon', 'label', 'flat', 'dense', 'to'] },
        'q-table': { template: '<div class="q-table"><slot /><slot name="loading" /><slot name="body" /><slot name="no-data" /></div>', props: ['rows', 'columns', 'loading', 'pagination', 'visibleColumns'] },
        'q-input': { template: '<input class="q-input" />', props: ['modelValue'] },
        'q-icon': { template: '<span class="q-icon" />' },
        'q-skeleton': { template: '<span class="q-skeleton" />' },
        'q-dialog': { template: '<div class="q-dialog"><slot /></div>', props: ['modelValue'] },
        'q-banner': { template: '<div class="q-banner"><slot /><slot name="action" /><slot name="avatar" /></div>' },
        'q-badge': { template: '<span class="q-badge"><slot /></span>' },
        'q-separator': { template: '<hr class="q-separator" />' },
        'q-linear-progress': { template: '<div class="q-linear-progress"><slot /></div>' },
        'q-checkbox': { template: '<input type="checkbox" class="q-checkbox" />' },
        'q-select': { template: '<select class="q-select" />' },
        'q-slider': { template: '<input type="range" class="q-slider" />' },
        'q-tooltip': { template: '<span class="q-tooltip"><slot /></span>' },
        'q-expansion-item': { template: '<div class="q-expansion-item"><slot /></div>' },
        'q-spinner': { template: '<span class="q-spinner" />' },
        'q-tr': { template: '<tr><slot /></tr>' },
        'q-td': { template: '<td><slot /></td>' },
        'q-item': { template: '<div class="q-item"><slot /></div>' },
        'q-item-section': { template: '<div class="q-item-section"><slot /></div>' },
        'q-item-label': { template: '<div class="q-item-label"><slot /></div>' },
        'q-list': { template: '<div class="q-list"><slot /></div>' },
        'q-menu': { template: '<div class="q-menu"><slot /></div>' },
        'q-option-group': { template: '<div class="q-option-group" />' },
        'q-btn-dropdown': { template: '<div class="q-btn-dropdown"><slot /></div>' },
        ...(globalOpts.stubs || {}),
        ...options.stubs,
      },
      ...globalOpts,
    },
  });
}

export function shallowMountWithQuasar(component, options = {}) {
  const globalOpts = options.global || {};
  return shallowMount(component, {
    ...options,
    global: {
      plugins: [i18n, ...(globalOpts.plugins || [])],
      mocks: {
        $q: quasarMock,
        ...(globalOpts.mocks || {}),
      },
      stubs: {
        teleport: true,
        ...(globalOpts.stubs || {}),
        ...options.stubs,
      },
      ...globalOpts,
    },
  });
}
