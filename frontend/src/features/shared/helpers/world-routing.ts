import { markRaw } from 'vue'
import type { RouteRecordRaw, Router } from 'vue-router'
import WorldSelector from '../components/WorldSelector.vue'
import { ensureWorlds, useWorld } from './world-state'

/**
 * Rende `meta.hidden` dinamico per le route con `meta.capability` (le schede della dashboard e le voci di
 * menu lo leggono dentro un `computed`, quindi seguono il mondo attivo). Le route già `hidden` restano tali.
 *
 * @param routes - route dichiarate (si visitano anche i figli)
 */
function hideByCapability(routes: readonly RouteRecordRaw[]): void {
  const { supports } = useWorld()
  for (const route of routes) {
    const meta = route.meta
    if (meta?.capability && meta.hidden !== true) {
      const capability = meta.capability
      Object.defineProperty(meta, 'hidden', { get: () => !supports(capability), enumerable: true, configurable: true })
    }
    if (route.children) hideByCapability(route.children)
  }
}

/**
 * Collega l'editor ai mondi: guardia sulle route con `meta.capability`, voci nascoste per capability e
 * selettore di mondo nella barra dell'app (via `meta.appBarComponents` del layout).
 *
 * @param router - router creato da `createPachiRouter`
 */
export function installWorldRouting(router: Router): void {
  hideByCapability(router.options.routes)
  const layout = router.getRoutes().find((route) => route.path === '/')
  if (layout) layout.meta.appBarComponents = [markRaw(WorldSelector)]

  const { supports } = useWorld()
  router.beforeEach(async (to) => {
    if (!to.meta.capability) return true
    await ensureWorlds()
    return supports(to.meta.capability) ? true : '/'
  })
}
