import type { RouteRecordRaw } from 'vue-router'
import { mdiHeartPulse } from '@quasar/extras/mdi-v7'

/** Stato dell'editor: `/status` (backend raggiungibile, versione, mondi configurati). */
export default [
  {
    path: '/status',
    meta: { titleKey: 'status.title', descriptionKey: 'status.description', icon: mdiHeartPulse, order: 1 },
    component: () => import('./pages/StatusPage.vue'),
  },
] as RouteRecordRaw[]
