import { definePachiConfig } from "@ilpachi/pachifastquasar";
import type { PachiConfigInput } from "@ilpachi/pachifastquasar";
import logoUrl from "src/assets/logo.png";

/**
 * Configurazione di base dell'app (logo, componenti, voci di menu, impostazioni proprie). Le variabili
 * `QCLI_*` / `VITE_*` (vedi `.env.example`) la sovrascrivono SOLO per le impostazioni che definiscono:
 * ciò che non è nell'ambiente resta come scritto qui.
 */
const baseConfig: PachiConfigInput = {
  app: { title: "Pachimud Editor", logoSize: "64px" }, // la mascotte ha dettagli fini: leggibile solo da ~48px
  // http: { envelope: false },             // backend con PACHIFAST_ENVELOPE_ENABLED=false
  logo: `img:${logoUrl}`, // mascotte pachimudeditor (PNG ritagliato e ottimizzato)
  // components: { layout, loginPage, errorPage },
  // menuItems: [{ label: 'Guida', to: '/guida', order: 80 }],
};

/** Condivisa da boot e router. */
export const pachiConfig: PachiConfigInput = definePachiConfig(baseConfig, import.meta.env);
