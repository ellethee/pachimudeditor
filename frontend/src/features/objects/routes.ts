import type { RouteRecordRaw } from 'vue-router'
import { mdiShape } from '@quasar/extras/mdi-v7'

export default [
  {
    path: '/objects',
    meta: {
      title: 'Oggetti',
      titleKey: 'objects.title',
      descriptionKey: 'objects.description',
      icon: mdiShape,
      order: 40,
    },
    component: () => import('./pages/ObjectsIndexPage.vue'),
  },
  {
    // Dettaglio oggetto (maschera di modifica inline): fuori da menu e dashboard.
    path: '/objects/:id(\\d+)',
    meta: { titleKey: 'objects.detail.title', icon: mdiShape, hidden: true, pageScroll: true },
    component: () => import('./pages/ObjectDetailPage.vue'),
  },
] as RouteRecordRaw[]
