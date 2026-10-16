import { defineBoot } from '#q-app'
import { composePachiMessages, createPachiApp, AuthManager } from '@ilpachi/pachifastquasar'
import { setPachiProfileUser } from '@ilpachi/fastquasar-profile'
import { pachiConfig } from 'src/pachi-config'
import { installWorldHeader } from 'src/features/shared/helpers/world-http'
import 'src/css/app.scss'

/** Boot: installa la shell (config, HTTP, i18n con generated/overrides/feature dell'app). */
export default defineBoot(ctx => {
  // X-World su ogni richiesta /api (il mondo attivo lo sceglie il selettore nella barra dell'app)
  installWorldHeader()
  createPachiApp(ctx, {
    config: pachiConfig,
    messages: composePachiMessages({
      generated: import.meta.glob('../i18n/generated/*.json', { eager: true, import: 'default' }),
      overrides: import.meta.glob('../i18n/overrides/*.{ts,json}', {
        eager: true,
        import: 'default'
      }),
      locales: import.meta.glob('../i18n/locales/*.ts', { eager: true, import: 'default' }),
      features: import.meta.glob('/src/features/**/locales/*.ts', {
        eager: true,
        import: 'default'
      })
    })
  })

  // Profilo: la pagina legge l'utente da qui (reattivo: lo store dell'auth). Con auth disattivata
  // o senza sessione l'utente è null e la pagina resta vuota.
  setPachiProfileUser(() => {
    const user = AuthManager.getInstance().userInfo
    return user ? { ...user, email: user.email ?? '' } : null
  })
})
