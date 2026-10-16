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
