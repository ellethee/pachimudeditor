/** Messaggi italiani della feature (lingua di riferimento). */
export default {
  boards: {
    title: 'Bacheche',
    description: 'Le bacheche del gioco e i loro messaggi; della posta solo quante lettere aspettano ogni giocatore',
    tabs: { boards: 'Bacheche', mail: 'Posta' },
    refresh: 'Ricarica',
    noTable: 'Il database del gioco non ha la tabella delle bacheche: aggiorna lo schema del gioco (pachimud db upgrade).',
    noMailTable: 'Il database del gioco non ha la tabella della posta: aggiorna lo schema del gioco (pachimud db upgrade).',
    empty: 'Nessuna bacheca.',
    columns: { boardId: 'Bacheca', objects: 'Oggetti', count: 'Messaggi', limit: 'Limite' },
    orphan: 'senza oggetto',
    noObjects: 'nessun oggetto',
    search: 'Cerca (autore, titolo, testo)',
    back: 'Tutte le bacheche',
    messages: 'Messaggi di «{id}»',
    noMessages: 'Nessun messaggio.',
    message: { number: 'N.', author: 'Autore', date: 'Data', title: 'Titolo' },
    readOnlyNote: 'Sola lettura: per cancellare i messaggi serve il canale live del gioco.',
    mail: {
      privacy: 'Per privacy si vede solo quante lettere aspettano ogni giocatore, mai il testo.',
      total: 'Lettere in attesa: {count}',
      recipient: 'Destinatario',
      count: 'Lettere',
      empty: 'Nessuna lettera in attesa.',
      search: 'Cerca destinatario',
    },
  },
}
