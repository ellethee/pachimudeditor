import type { RouteRecordRaw } from 'vue-router'
import { mdiEarth, mdiFamilyTree, mdiMagnify } from '@quasar/extras/mdi-v7'

/**
 * Route della feature mondo: `/world` (panoramica, landing dell'editor), `/world/graph` (grafo tra
 * zone) e `/world/search` (ricerca globale). Sorelle (non annidate) così compaiono tutte come schede.
 */
export default [
  {
    path: '/world',
    meta: {
      capability: 'supportsWorldOverview',
      titleKey: 'world.title',
      descriptionKey: 'world.description',
      icon: mdiEarth,
      order: 5,
    },
    component: () => import('./pages/WorldOverviewPage.vue'),
  },
  {
    path: '/world/graph',
    meta: {
      capability: 'supportsWorldOverview',
      titleKey: 'world.graph.title',
      descriptionKey: 'world.graph.description',
      icon: mdiFamilyTree,
      order: 6,
    },
    component: () => import('./pages/ZoneGraphPage.vue'),
  },
  {
    path: '/world/search',
    meta: {
      capability: 'supportsWorldOverview',
      titleKey: 'world.search.title',
      descriptionKey: 'world.search.description',
      icon: mdiMagnify,
      order: 7,
    },
    component: () => import('./pages/WorldSearchPage.vue'),
  },
] as RouteRecordRaw[]
