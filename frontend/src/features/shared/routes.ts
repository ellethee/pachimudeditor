import type { RouteRecordRaw } from 'vue-router'
import { mdiEarthOff } from '@quasar/extras/mdi-v7'

/** Pagina "nessun mondo configurato": fuori da menu e dashboard, vi si arriva dal selettore di mondo. */
export default [
  {
    path: '/no-worlds',
    meta: { titleKey: 'worlds.none.title', icon: mdiEarthOff, hidden: true },
    component: () => import('./pages/NoWorldsPage.vue'),
  },
] as RouteRecordRaw[]
