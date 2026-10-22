# Frontend

L'interfaccia e' una SPA [Quasar](https://quasar.dev) (Vue 3 + TypeScript) costruita su
[`@ilpachi/pachifastquasar`](https://www.npmjs.com/package/@ilpachi/pachifastquasar). Nel pacchetto `pachimudeditor` e' gia'
buildata e viene servita dal backend alla radice del dominio (`/assets/...`: un eventuale reverse proxy non deve usare un prefisso).

## Pagine

| Area | Cosa si fa | Disponibile |
| --- | --- | --- |
| Zone, stanze, mob, oggetti | elenco, ricerca, creazione, modifica, clonazione, script di reset, uscite | sempre (mondo scrivibile per le modifiche) |
| Oggetti (lista) | «Tutte le zone» di default (la creazione chiede la zona), colonne scelte dal viewer (zona, peso, costo, affitto, valori 0-3, indossabile in, effetti; salvate nel browser, poche su telefono) tutte ordinabili lato server, barra filtri (tipo, indossa in, flag extra, intervalli numerici, apply degli effetti) con chip, «Azzera filtri» e stato nell'URL (`?zoneId=&objectType=1,2&minCost=100&wearFlag=take`) | sempre |
| Mondo | panoramica, grafo tra zone, ricerca trasversale | capability `supportsWorldOverview` |
| Istanze | mob e oggetti vivi nel gioco | capability `supportsInstances` |
| Giocatori | account, personaggi, inventario | capability `supportsPlayers` |
| Giocatori (file) | elenco e dettaglio dei giocatori salvati nei file del MUD, con inventario/equipaggiamento; pagina `/player-files` guidata dal descrittore dell'adapter, avviso «il server potrebbe essere in esecuzione»; modifica dei campi (salvataggio con conferma se il server e' acceso) e dell'inventario (aggiungi da catalogo, cambia slot, togli) nei mondi non `read_only` | capability `supportsPlayerRecords` (inventario: `supportsPlayerInventory`; scrittura: `supportsPlayerWrite`, `supportsPlayerInventoryWrite`) |
| Canale live | nella pagina Giocatori (file): chip dello stato del canale, badge «online» (o «link morto»), per un giocatore connesso la modifica passa dal canale (salvataggio nel gioco di default, avvertenza e conferma esplicita per i livelli >= 51) il pannello «Server live» (giocatori connessi, uptime e contatori, reset di una zona da elenco con conferma, crea mob/oggetti in una stanza o a un giocatore, messaggi) e, per un giocatore connesso, la scheda **Inventario LIVE** (badge «LIVE», equipaggiamento/inventario/contenuti con annidamento, aggiunta da un elenco filtrabile con avviso `vnum_not_saveable`, rimozione con conferma, modifica dell'oggetto: parole chiave, descrizioni, 4 valori etichettati dal tipo, peso, extra flag, 5 affect, timer; `stale_ref` = messaggio chiaro, elenco ricaricato e input conservato). Dopo aver creato un oggetto per un giocatore da «Server live» c'e' «Modifica»; per un oggetto creato in una stanza no (limite del protocollo: gli oggetti a terra non sono indirizzabili). Nell'inventario su file gli oggetti con vnum > 32767 non sono selezionabili («non salvabile nel rent»). Solo superuser; con il canale spento stato chiaro e ripiego sui file; mondo `read_only` senza controlli di scrittura | capability `supportsLive` (inventario live: `supportsLiveInventory` + feature `inventory` del MUD) |
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
