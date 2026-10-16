import { defineRouter } from '#q-app'
import { createPachiRouter } from '@ilpachi/pachifastquasar'
import { pachiConfig } from 'src/pachi-config'
import { installWorldRouting } from 'src/features/shared/helpers/world-routing'

export default defineRouter(function (/* { store, ssrContext } */) {
  const router = createPachiRouter({
    config: pachiConfig,
    env: import.meta.env,
    mode: import.meta.env.QUASAR_VUE_ROUTER_MODE,
    base: import.meta.env.QUASAR_VUE_ROUTER_BASE,
    features: import.meta.glob('/src/features/**/routes.ts', { eager: true, import: 'default' }),
    packages: import.meta.glob('/node_modules/@ilpachi/*/{routes,dist/routes,src/routes}.{ts,js}', {
      eager: true,
      import: 'default'
    }),
    menus: import.meta.glob('/node_modules/@ilpachi/*/{menu,dist/menu,src/menu}.{ts,js}', {
      eager: true,
      import: 'default'
    })
  })
  installWorldRouting(router)
  return router
})
