const routes = [
  {
    path: '/',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ path: '', component: () => import('pages/MainDashboard.vue') }],
    beforeEnter() {
      location.href = '/ui/dashboard'
    },
  },
  {
    path: '/ui/trigger',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ name: 'trigger', path: '', component: () => import('pages/ActionTrigger.vue') }],
  },
  {
    path: '/ui/dashboard',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ name: 'dashboard', path: '', component: () => import('pages/MainDashboard.vue') }],
    meta: {
      showHome: false,
      showMainNavDrawer: true,
    },
  },
  {
    path: '/ui/data-panels',
    props: true,
    component: () => import('layouts/MainLayout.vue'),
    children: [{ name: 'data-panels', path: '', component: () => import('pages/DataPanels.vue') }],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    },
  },
  {
    path: '/ui/settings-library',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ path: '', component: () => import('pages/SettingsLibrary.vue') }],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    },
  },
  {
    path: '/ui/settings-workers',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ path: '', component: () => import('pages/SettingsWorkers.vue') }],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    },
  },
  {
    path: '/ui/settings-plugins',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ path: '', component: () => import('pages/SettingsPlugins.vue') }],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    },
  },
  {
    path: '/ui/settings-link',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ path: '', component: () => import('pages/SettingsLink.vue') }],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    },
  },
  {
    path: '/ui/settings-notifications',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ path: '', component: () => import('pages/SettingsNotifications.vue') }],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    },
  },
  {
    path: '/ui/compression',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ name: 'compression', path: '', component: () => import('pages/CompressionDashboard.vue') }],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    },
  },
  {
    path: '/ui/health',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ name: 'health', path: '', component: () => import('pages/HealthCheck.vue') }],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    },
  },
  {
    path: '/ui/history',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ name: 'history', path: '', component: () => import('pages/TaskHistory.vue') }],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    },
  },
  {
    path: '/ui/approval',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ name: 'approval', path: '', component: () => import('pages/ApprovalQueue.vue') }],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    },
  },
  {
    path: '/ui/preview',
    component: () => import('layouts/MainLayout.vue'),
    children: [{ name: 'preview', path: '', component: () => import('pages/PreviewCompare.vue') }],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    },
  },
  // Always leave this as last one,
  // but you can also remove it
  {
    path: '/:catchAll(.*)*',
    component: () => import('pages/ErrorNotFound.vue'),
  },
]

export default routes
