import type { RouteRecordRaw } from 'vue-router'
import { mdiClipboardTextOutline } from '@quasar/extras/mdi-v7'

/** Bacheche e posta (sola lettura): solo nei mondi che le dichiarano (pachimud con DB dei giocatori). */
export default [
  {
    path: '/boards',
    meta: {
      capability: 'supportsBoards',
      titleKey: 'boards.title',
      descriptionKey: 'boards.description',
      icon: mdiClipboardTextOutline,
      order: 36,
    },
    component: () => import('./pages/BoardsPage.vue'),
  },
] as RouteRecordRaw[]
