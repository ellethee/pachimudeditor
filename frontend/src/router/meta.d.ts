import 'vue-router'
import type { WorldCapability } from 'src/features/shared/types/worlds'

declare module 'vue-router' {
  interface RouteMeta {
    /** Capability del mondo necessaria: senza, la route è nascosta da menu/dashboard e la navigazione rimanda a `/`. */
    capability?: WorldCapability
  }
}
