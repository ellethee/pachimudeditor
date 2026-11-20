import type { RouteRecordRaw } from 'vue-router'
import { mdiStorefront } from '@quasar/extras/mdi-v7'

/** Elenco dei negozi (i mob con il campo `shop`): solo nei mondi che dichiarano i contenuti YAML (pachimud). */
export default [
  {
    path: '/shops',
    meta: {
      capability: 'supportsContentRaces',
      titleKey: 'shops.title',
      descriptionKey: 'shops.description',
      icon: mdiStorefront,
      order: 35,
    },
    component: () => import('./pages/ShopsPage.vue'),
  },
] as RouteRecordRaw[]
