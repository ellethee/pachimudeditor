# frontend



App Quasar basata su [`@ilpachi/pachifastquasar`](https://www.npmjs.com/package/@ilpachi/pachifastquasar) (generata con `pachifq create`).

```bash
pnpm install
pnpm dev                              # dev server (auth attiva di default)
QCLI_AUTH_ENABLED=false pnpm dev      # senza auth
pnpm build                            # build produzione (dist/spa)
pnpm typecheck
```

- Configurazione: variabili `QCLI_*` in `src/.env` (vedi `src/.env.example`) e `src/pachi-config.ts`.
- Backend con `PACHIFAST_ENVELOPE_ENABLED=false` (risposte senza envelope): `QCLI_HTTP_ENVELOPE=false` in `src/.env`. Il client HTTP è `@ilpachi/use-alova`.
- Nuove feature: `pachifq new feature <nome>` (crea `src/features/<nome>/`, raccolta in automatico dal router).
- Nuove lingue: `pachifq new locale <codice>`.
