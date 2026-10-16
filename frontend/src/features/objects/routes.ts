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
] as RouteRecordRaw[]
