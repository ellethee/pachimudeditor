import type { RouteRecordRaw } from 'vue-router'
import { mdiTransfer } from '@quasar/extras/mdi-v7'
import { useWorld } from '../shared/helpers/world-state'

const meta = {
  titleKey: 'convert.title',
  descriptionKey: 'convert.description',
  icon: mdiTransfer,
  order: 90,
} as RouteRecordRaw['meta'] & { hidden?: boolean }

// La conversione ha senso solo con almeno due mondi: `hidden` e' reattivo (letto da menu/dashboard in un computed).
Object.defineProperty(meta, 'hidden', {
  get: () => useWorld().loaded.value && useWorld().worlds.value.length < 2,
  enumerable: true,
  configurable: true,
})

export default [
  {
    path: '/convert',
    meta,
    component: () => import('./pages/ConvertPage.vue'),
  },
] as RouteRecordRaw[]
