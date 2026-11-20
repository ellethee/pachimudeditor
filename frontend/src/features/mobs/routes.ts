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
  {
    // Dettaglio mob (maschera di modifica inline): fuori da menu e dashboard.
    path: '/mobs/:id(\\d+)',
    meta: { titleKey: 'mobs.detail.title', icon: mdiPaw, hidden: true, pageScroll: true },
    component: () => import('./pages/MobDetailPage.vue'),
  },
] as RouteRecordRaw[]
