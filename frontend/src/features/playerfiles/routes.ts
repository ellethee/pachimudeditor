import type { RouteRecordRaw } from 'vue-router'
import { mdiAccountSearch } from '@quasar/extras/mdi-v7'

/**
 * Giocatori dei mondi su file (sola lettura), guidati dal descrittore dell'adapter. Convive con `/players`
 * (account/personaggi del DB pachimud): ciascuna voce compare solo se il mondo ha la sua capability.
 */
export default [
  {
    path: '/player-files',
    meta: {
      capability: 'supportsPlayerRecords',
      titleKey: 'playerFiles.title',
      descriptionKey: 'playerFiles.description',
      icon: mdiAccountSearch,
      order: 51,
    },
    component: () => import('./pages/PlayerFilesPage.vue'),
  },
] as RouteRecordRaw[]
