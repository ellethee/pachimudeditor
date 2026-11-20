/** English messages for the feature. */
export default {
  boards: {
    title: 'Boards',
    description: 'The game boards and their messages; for mail only how many letters each player has waiting',
    tabs: { boards: 'Boards', mail: 'Mail' },
    refresh: 'Reload',
    noTable: 'The game database has no board table: upgrade the game schema (pachimud db upgrade).',
    noMailTable: 'The game database has no mail table: upgrade the game schema (pachimud db upgrade).',
    empty: 'No boards.',
    columns: { boardId: 'Board', objects: 'Objects', count: 'Messages', limit: 'Limit' },
    orphan: 'no object',
    noObjects: 'no object',
    search: 'Search (author, title, text)',
    back: 'All boards',
    messages: 'Messages of «{id}»',
    noMessages: 'No messages.',
    message: { number: 'No.', author: 'Author', date: 'Date', title: 'Title' },
    readOnlyNote: 'Read only: deleting messages needs the game live channel.',
    mail: {
      privacy: 'For privacy only the number of letters waiting for each player is shown, never the text.',
      total: 'Letters waiting: {count}',
      recipient: 'Recipient',
      count: 'Letters',
      empty: 'No letters waiting.',
      search: 'Search recipient',
    },
  },
}
