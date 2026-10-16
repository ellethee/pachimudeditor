"""Messaggi dell'adapter Diku Modificato in it: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "dikumod.unsafe_text": "Testo non scrivibile nei file Diku Modificato: {reason}.",
    "dikumod.unknown_flag": "Flag «{name}» sconosciuto nella tabella {table}.",
    "dikumod.extra_unknown": "Chiave di extra «{key}» sconosciuta (note: {known}).",
    "dikumod.extra_invalid": "Valore non valido per extra «{key}».",
    "dikumod.extra_readonly": "La chiave di extra «{key}» è di sola lettura.",
    "dikumod.field_unsupported": "Il campo «{field}» non esiste in Diku Modificato: è ammesso solo il valore neutro.",
    "dikumod.unknown_race": "Razza «{name}» sconosciuta.",
    "dikumod.hp_not_dice": "Per questo tipo di mob i punti ferita sono «livello d8 + bonus» (livello {level}): i dadi non sono modificabili.",
    "dikumod.kind_change": "Il tipo di mob «{kind}» non è ammesso (non si passa da/verso il tipo S).",
    "dikumod.too_many_affects": "Un oggetto Diku Modificato ha al massimo 5 affect.",
    "dikumod.reset_invalid_slot": "Comando {loc}: slot di vestizione «{slot}» sconosciuto.",
    "dikumod.record_corrupted": "Il record {vnum} è corrotto nel file ({reason}) e non è modificabile da qui.",
    "dikumod.vnum_out_of_range": "Il vnum {vnum} non appartiene alla zona (range {bottom}-{top}).",
    "dikumod.zone_derived": "La zona di un contenuto Diku Modificato deriva dal vnum: il vnum {vnum} appartiene alla zona {expected}.",
    "dikumod.zone_bottom_derived": "Il vnum minimo di una zona Diku Modificato è il top della zona precedente + 1 (atteso {expected}, richiesto {bottom}).",
    "dikumod.zone_top_order": "Il top deve restare tra quello della zona precedente ({prev}) e quello della successiva ({next}).",
    "dikumod.zone_range_has_content": "Cambiare il top sposterebbe {count} stanze/mob/oggetti in un'altra zona.",
    "dikumod.zone_index_in_use": "Eliminare la zona sposterebbe gli indici di file per-zona (zones/<n>.zon).",
    "dikumod.override_vnum_locked": "Il vnum {vnum} ha un file per-vnum (rooms/ o objects/): il nome del file è l'identità, non si può cambiare qui.",
    "dikumod.no_shop_file": "Il mondo non ha {file}: impossibile creare un negozio.",
}
