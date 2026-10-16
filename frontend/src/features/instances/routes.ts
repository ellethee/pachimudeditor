import type { RouteRecordRaw } from 'vue-router'
import { mdiMapMarkerMultiple } from '@quasar/extras/mdi-v7'

export default [
  {
    path: '/instances',
    meta: {
      capability: 'supportsInstances',
      title: 'Istanze',
      titleKey: 'instances.title',
      descriptionKey: 'instances.description',
      icon: mdiMapMarkerMultiple,
      order: 60,
    },
    component: () => import('./pages/InstancesPage.vue'),
  },
] as RouteRecordRaw[]
