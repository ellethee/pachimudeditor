import type { RouteRecordRaw } from 'vue-router'
import { mdiDoor, mdiGraphOutline } from '@quasar/extras/mdi-v7'

/**
 * Route della feature stanze. Due route sorelle (non annidate) così entrambe compaiono come
 * schede nella dashboard: `/rooms` (lista + editor) e `/rooms/map` (mappa vue-flow della zona).
 */
export default [
  {
    path: '/rooms',
    meta: {
      title: 'Stanze',
      titleKey: 'rooms.title',
      descriptionKey: 'rooms.description',
      icon: mdiDoor,
      order: 20,
    },
    component: () => import('./pages/RoomsPage.vue'),
  },
  {
    // Dettaglio stanza (maschera di modifica inline): fuori da menu e dashboard.
    path: '/rooms/:id(\\d+)',
    meta: { titleKey: 'rooms.detail.title', icon: mdiDoor, hidden: true, pageScroll: true },
    component: () => import('./pages/RoomDetailPage.vue'),
  },
  {
    path: '/rooms/map',
    meta: {
      title: 'Mappa stanze',
      titleKey: 'rooms.map.title',
      descriptionKey: 'rooms.map.description',
      icon: mdiGraphOutline,
      order: 21,
    },
    component: () => import('./pages/RoomMapPage.vue'),
  },
] as RouteRecordRaw[]
