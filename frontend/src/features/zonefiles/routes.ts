import type { RouteRecordRaw } from 'vue-router'
import { mdiFileCodeOutline } from '@quasar/extras/mdi-v7'

export default [
  {
    path: '/zones/files',
    meta: {
      capability: 'supportsContentRaces',
      titleKey: 'zonefiles.title',
      descriptionKey: 'zonefiles.description',
      icon: mdiFileCodeOutline,
      order: 11,
    },
    component: () => import('./pages/ZoneFilesPage.vue'),
  },
] as RouteRecordRaw[]
