/*
 * livectl.h - canale di controllo live (protocollo livectl v1) per Diku Modificato (DikuMod1).
 * Specifica: docs/backend/live-control-protocol.md e docs/adapters/dikumod-live.md.
 */
#ifndef LIVECTL_H
#define LIVECTL_H

void livectl_init(void);     /* dopo boot_db(), prima di game_loop() */
void livectl_poll(void);     /* in coda a ogni iterazione di game_loop(), non bloccante */
void livectl_shutdown(void); /* registrata con atexit() da livectl_init() */

#endif
