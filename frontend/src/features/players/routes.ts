import type { RouteRecordRaw } from 'vue-router'
import { mdiAccountGroup } from '@quasar/extras/mdi-v7'

export default [
  {
    path: '/players',
    meta: {
      capability: 'supportsPlayers',
      title: 'Giocatori',
      titleKey: 'players.title',
      descriptionKey: 'players.description',
      icon: mdiAccountGroup,
      order: 50,
    },
    component: () => import('./pages/PlayersIndexPage.vue'),
  },
] as RouteRecordRaw[]
