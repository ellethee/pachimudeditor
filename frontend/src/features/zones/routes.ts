import type { RouteRecordRaw } from 'vue-router'
import { mdiMapMarkerRadius, mdiReplay } from '@quasar/extras/mdi-v7'

export default [
  {
    path: '/zones',
    meta: {
      titleKey: 'zones.title',
      descriptionKey: 'zones.description',
      icon: mdiMapMarkerRadius,
      order: 10,
    },
    component: () => import('./pages/ZonesPage.vue'),
  },
  {
    // Script di reset di una zona: figlia logica di /zones, ma record separato per non trasformare
    // /zones in una dashboard di card (hidden: fuori da menu e dashboard).
    path: '/zones/:id(-?\\d+)/resets',
    meta: {
      capability: 'supportsResetScripts',
      titleKey: 'zones.resets.title',
      icon: mdiReplay,
      hidden: true,
      pageScroll: true,
    },
    component: () => import('./pages/ZoneResetsPage.vue'),
  },
] as RouteRecordRaw[]
