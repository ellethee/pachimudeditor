# Frontend

L'interfaccia e' una SPA [Quasar](https://quasar.dev) (Vue 3 + TypeScript) costruita su
[`@ilpachi/pachifastquasar`](https://www.npmjs.com/package/@ilpachi/pachifastquasar). Nel pacchetto `pachimudeditor` e' gia'
buildata e viene servita dal backend alla radice del dominio (`/assets/...`: un eventuale reverse proxy non deve usare un prefisso).

## Pagine

| Area | Cosa si fa | Disponibile |
| --- | --- | --- |
| Zone, stanze, mob, oggetti | elenco, ricerca, creazione, modifica, clonazione, script di reset, uscite | sempre (mondo scrivibile per le modifiche) |
| Mondo | panoramica, grafo tra zone, ricerca trasversale | capability `supportsWorldOverview` |
| Istanze | mob e oggetti vivi nel gioco | capability `supportsInstances` |
| Giocatori | account, personaggi, inventario | capability `supportsPlayers` |
| Trasferimento | export/import di zone in YAML | capability `supportsTransfer` |
| Contenuti | razze e classi | capability `supportsContentRaces` |
| Conversione | copia di zone fra due mondi | almeno due mondi configurati |

Con piu' mondi configurati un selettore sceglie su quale lavorare (header `X-World`). Le pagine specifiche compaiono solo se
l'adapter del mondo attivo dichiara la capability corrispondente (vedi [adapter](../adapters/sdk.md)). Senza nessun mondo
la UI mostra "Nessun mondo configurato" con le istruzioni.

## Sviluppo del frontend

I sorgenti sono in `frontend/` del repository.

```bash
pnpm install
pnpm dev          # http://localhost:9010, proxy /api verso il backend su :8123
pnpm typecheck
pnpm build        # produzione; per includerla nel pacchetto: pachimudeditor build-frontend
```

Configurazione: variabili `QCLI_*` in `src/.env` e `src/pachi-config.ts`. Il client HTTP e' `@ilpachi/use-alova`; con
`PACHIFAST_ENVELOPE_ENABLED=false` nel backend serve `QCLI_HTTP_ENVELOPE=false`.
