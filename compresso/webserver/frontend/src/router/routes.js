
const routes = [
  {
    path: '/',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/MainDashboard.vue') }
    ],
    beforeEnter() {
      location.href = '/ui/dashboard'
    }
  },
  {
    name: 'trigger',
    path: '/ui/trigger',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/ActionTrigger.vue') }
    ]
  },
  {
    name: 'dashboard',
    path: '/ui/dashboard',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/MainDashboard.vue') }
    ],
    meta: {
      showHome: false,
      showMainNavDrawer: true,
    }
  },
  {
    name: 'data-panels',
    path: '/ui/data-panels',
    props: true,
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/DataPanels.vue') }
    ],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    }
  },
  {
    path: '/ui/settings-library',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/SettingsLibrary.vue') }
    ],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    }
  },
  {
    path: '/ui/settings-workers',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/SettingsWorkers.vue') }
    ],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    }
  },
  {
    path: '/ui/settings-plugins',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/SettingsPlugins.vue') }
    ],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    }
  },
  {
    path: '/ui/settings-link',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/SettingsLink.vue') }
    ],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    }
  },
  {
    name: 'compression',
    path: '/ui/compression',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/CompressionDashboard.vue') }
    ],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    }
  },
  {
    name: 'health',
    path: '/ui/health',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/HealthCheck.vue') }
    ],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    }
  },
  {
    name: 'approval',
    path: '/ui/approval',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/ApprovalQueue.vue') }
    ],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    }
  },
  {
    name: 'preview',
    path: '/ui/preview',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/PreviewCompare.vue') }
    ],
    meta: {
      showHome: true,
      showMainNavDrawer: true,
    }
  },
  // Always leave this as last one,
  // but you can also remove it
  {
    path: '/:catchAll(.*)*',
    component: () => import('pages/ErrorNotFound.vue')
  }
]

export default routes
