import type { RouteRecordRaw } from 'vue-router'
import { mdiPaw } from '@quasar/extras/mdi-v7'

export default [
  {
    path: '/mobs',
    meta: {
      title: 'Mob',
      titleKey: 'mobs.title',
      descriptionKey: 'mobs.description',
      icon: mdiPaw,
      order: 30,
    },
    component: () => import('./pages/MobsIndexPage.vue'),
  },
] as RouteRecordRaw[]
