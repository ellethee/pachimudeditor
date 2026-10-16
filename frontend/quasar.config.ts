// Configurazione di Quasar: il preset di @ilpachi/pachifastquasar fa tutto (boot, stili, alias, env, proxy).
// Gli override opzionali si passano come primo argomento, le opzioni del preset come secondo.
// https://v2.quasar.dev/quasar-cli-vite/quasar-config-file
import { loadEnv } from "vite";
import { definePachiQuasarConfig } from "@ilpachi/pachifastquasar/quasar";

// Il preset legge QCLI_PROXY_TARGET solo da process.env: lo leggiamo da `src/.env` (envDir dell'app),
// lasciando la precedenza a una variabile d'ambiente già impostata.
const env = loadEnv("development", new URL("./src", import.meta.url).pathname, "QCLI_");

export default definePachiQuasarConfig(
  { devServer: { port: 9010 } },
  { proxyTarget: process.env.QCLI_PROXY_TARGET ?? env.QCLI_PROXY_TARGET ?? "http://localhost:8123" }
);
