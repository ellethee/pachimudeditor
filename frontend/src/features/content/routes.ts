import type { RouteRecordRaw } from 'vue-router'
import { mdiAccountGroup, mdiSwordCross } from '@quasar/extras/mdi-v7'

export default [
  {
    path: '/content/races',
    meta: {
      capability: 'supportsContentRaces',
      titleKey: 'content.races.title',
      descriptionKey: 'content.races.description',
      icon: mdiAccountGroup,
      order: 80,
    },
    component: () => import('./pages/RacesPage.vue'),
  },
  {
    path: '/content/classes',
    meta: {
      capability: 'supportsContentRaces',
      titleKey: 'content.classes.title',
      descriptionKey: 'content.classes.description',
      icon: mdiSwordCross,
      order: 81,
    },
    component: () => import('./pages/ClassesPage.vue'),
  },
] as RouteRecordRaw[]
