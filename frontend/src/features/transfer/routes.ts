import type { RouteRecordRaw } from 'vue-router'
import { mdiSwapVertical } from '@quasar/extras/mdi-v7'

export default [
  {
    path: '/transfer',
    meta: {
      capability: 'supportsTransfer',
      titleKey: 'transfer.title',
      descriptionKey: 'transfer.description',
      icon: mdiSwapVertical,
      order: 70,
    },
    component: () => import('./pages/TransferPage.vue'),
  },
] as RouteRecordRaw[]
