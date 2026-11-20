import type { RouteRecordRaw } from 'vue-router'
import { mdiBed } from '@quasar/extras/mdi-v7'

/** Elenco delle locande (i mob `receptionist`): solo nei mondi che dichiarano i contenuti YAML (pachimud). */
export default [
  {
    path: '/inns',
    meta: {
      capability: 'supportsContentRaces',
      titleKey: 'inns.title',
      descriptionKey: 'inns.description',
      icon: mdiBed,
      order: 36,
    },
    component: () => import('./pages/InnsPage.vue'),
  },
] as RouteRecordRaw[]
