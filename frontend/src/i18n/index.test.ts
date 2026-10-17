import { describe, expect, it } from 'vitest'
import {
  formatInteger,
  formatUtcDateTime,
  initializeLocale,
  i18n,
  localeMessageKey,
  localeStorageKey,
  resolveLocale,
  setLocale,
  supportedLocales,
  translateText,
} from './index'
import en from './locales/en.json'
import de from './locales/de.json'
import fr from './locales/fr.json'
import es from './locales/es.json'
import itLocale from './locales/it.json'

describe('localization foundation', () => {
  it('negotiates the first supported browser language and falls back to English', () => {
    expect(resolveLocale(['pt-BR', 'de-AT'])).toBe('de')
    expect(resolveLocale(['es-MX', 'fr'])).toBe('es')
    expect(resolveLocale(['pt-BR'])).toBe('en')
    expect(resolveLocale(['de'], 'it')).toBe('it')
    expect(resolveLocale(['de'], 'invalid')).toBe('de')
  })

  it('loads and persists a manual language choice and updates the document language', async () => {
    const values = new Map<string, string>()
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    } as unknown as Storage

    expect(await initializeLocale(['fr-CA'], storage)).toBe('fr')
    await setLocale('de', storage)

    expect(values.get(localeStorageKey)).toBe('de')
    expect(i18n.global.locale.value).toBe('de')
    expect(document.documentElement.lang).toBe('de')
    expect(translateText('Published results')).toBe(
      'Veröffentlichte Ergebnisse',
    )
  })

  it('keeps English as the runtime fallback when a locale lacks a key', async () => {
    await setLocale('it', undefined)
    expect(translateText('Open main menu')).toBe('Apri il menu principale')
    expect(i18n.global.fallbackLocale.value).toBe('en')
  })

  it('keeps all five locale catalogs in exact key parity with English', () => {
    const catalogs = [de, fr, es, itLocale]
    const englishKeys = Object.keys(en).sort()
    for (const catalog of catalogs) {
      expect(Object.keys(catalog).sort()).toEqual(englishKeys)
      expect(Object.values(catalog).every(Boolean)).toBe(true)
    }
    expect(supportedLocales).toEqual(['en', 'de', 'fr', 'es', 'it'])
  })

  it('translates shared navigation copy in every launch locale', async () => {
    const expected = {
      en: 'Published results',
      de: 'Veröffentlichte Ergebnisse',
      fr: 'Résultats publiés',
      es: 'Resultados publicados',
      it: 'Risultati pubblicati',
    } as const
    for (const locale of supportedLocales) {
      await setLocale(locale, undefined)
      expect(translateText('Published results')).toBe(expected[locale])
    }
    await setLocale('en', undefined)
  })

  it('translates the generated contest summary notice in every launch locale', async () => {
    const source =
      'This summary is automatically generated from the ruleset and may be imprecise. Refer to the contest’s official published rules for the authoritative requirements. The English version of this description remains authoritative.'
    const expected = {
      en: 'This summary is automatically generated from the ruleset and may be imprecise. Refer to the contest’s official published rules for the authoritative requirements. The English version of this description remains authoritative.',
      de: 'Diese Zusammenfassung wird automatisch aus dem Regelsatz erstellt und kann ungenau sein. Maßgeblich sind die offiziell veröffentlichten Wettbewerbsregeln. Die englische Fassung dieser Beschreibung bleibt maßgeblich.',
      fr: 'Ce résumé est généré automatiquement à partir du jeu de règles et peut manquer de précision. Consultez le règlement officiel publié du concours pour connaître les exigences faisant autorité. La version anglaise de cette description reste la référence.',
      es: 'Este resumen se genera automáticamente a partir del conjunto de reglas y puede ser impreciso. Consulte las reglas oficiales publicadas del concurso para conocer los requisitos definitivos. La versión en inglés de esta descripción sigue siendo la versión de referencia.',
      it: 'Questo riepilogo è generato automaticamente dal regolamento e potrebbe essere impreciso. Per i requisiti ufficiali, consultare il regolamento pubblicato del concorso. La versione inglese di questa descrizione resta quella di riferimento.',
    } as const

    for (const locale of supportedLocales) {
      await setLocale(locale, undefined)
      expect(translateText(source)).toBe(expected[locale])
    }
    await setLocale('en', undefined)
  })

  it('translates the warning for incomplete saved Cabrillo templates', async () => {
    const source =
      'The saved ruleset has an incomplete Cabrillo QSO column template. This example uses standard Cabrillo columns; log uploads may be rejected until a contest manager fixes the ruleset.'
    const expected = {
      en: source,
      de: 'Der gespeicherte Regelsatz enthält eine unvollständige Cabrillo-QSO-Spaltenvorlage. Dieses Beispiel verwendet die standardmäßigen Cabrillo-Spalten; Log-Uploads können abgelehnt werden, bis ein Contest-Manager den Regelsatz korrigiert.',
      fr: 'Le jeu de règles enregistré possède un modèle de colonnes QSO Cabrillo incomplet. Cet exemple utilise les colonnes Cabrillo standard ; les journaux peuvent être rejetés tant qu’un responsable du concours n’a pas corrigé le jeu de règles.',
      es: 'El conjunto de reglas guardado tiene una plantilla incompleta de columnas QSO de Cabrillo. Este ejemplo usa las columnas estándar de Cabrillo; los registros podrían rechazarse hasta que un administrador del concurso corrija el conjunto de reglas.',
      it: 'Il regolamento salvato contiene un modello incompleto di colonne QSO Cabrillo. Questo esempio usa le colonne Cabrillo standard; i log potrebbero essere rifiutati finché un responsabile del contest non corregge il regolamento.',
    } as const

    for (const locale of supportedLocales) {
      await setLocale(locale, undefined)
      expect(translateText(source)).toBe(expected[locale])
    }
    await setLocale('en', undefined)
  })

  it('uses locale-aware UTC timestamps and integer-only number formatting', async () => {
    await setLocale('de', undefined)
    expect(formatUtcDateTime('2026-10-17T14:05:00Z')).toContain('UTC')
    expect(formatInteger(123456)).toBe('123.456')
    expect(() => formatInteger(12.5)).toThrow(RangeError)
    await setLocale('en', undefined)
    expect(
      formatUtcDateTime('2026-10-17T00:30:00Z', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }),
    ).toBe('17 Oct 2026, 00:30 UTC')
  })

  it('uses deterministic source-text message identifiers', () => {
    expect(localeMessageKey('Published results')).toBe('s_20921423')
  })
})
