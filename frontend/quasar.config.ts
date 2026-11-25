// Configurazione di Quasar: il preset di @ilpachi/pachifastquasar fa tutto (boot, stili, alias, env, proxy).
// Gli override opzionali si passano come primo argomento, le opzioni del preset come secondo.
// https://v2.quasar.dev/quasar-cli-vite/quasar-config-file
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import { loadEnv } from "vite";
import { definePachiQuasarConfig } from "@ilpachi/pachifastquasar/quasar";

// Il preset legge QCLI_PROXY_TARGET solo da process.env: lo leggiamo da `src/.env` (envDir dell'app),
// lasciando la precedenza a una variabile d'ambiente già impostata.
const env = loadEnv("development", new URL("./src", import.meta.url).pathname, "QCLI_");

// I temi sono attivi di default quando la versione installata di pachifastquasar li ha (esporta `themes.css`); con
// QCLI_APP_THEMES=false si disattivano, con una versione piu' vecchia (senza CSS dei temi) la build resta com'era.
const themesCss = (() => {
  try {
    return createRequire(import.meta.url).resolve("@ilpachi/pachifastquasar/themes.css");
  } catch {
    return undefined;
  }
})();
const requested = process.env.QCLI_APP_THEMES ?? env.QCLI_APP_THEMES;
const themes = requested === undefined ? themesCss !== undefined && existsSync(themesCss) : requested === "true";
if (themes && requested === undefined) process.env.QCLI_APP_THEMES = "true";

export default definePachiQuasarConfig(
  {
    devServer: { port: 9010 },
    ...(themes ? { css: ["~@ilpachi/pachifastquasar/styles.css", "~@ilpachi/pachifastquasar/themes.css"] } : {})
  },
  { proxyTarget: process.env.QCLI_PROXY_TARGET ?? env.QCLI_PROXY_TARGET ?? "http://localhost:8123" }
);
