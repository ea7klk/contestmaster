import { createI18n, type I18nOptions } from 'vue-i18n'
import en from './locales/en.json'

export const supportedLocales = ['en', 'de', 'fr', 'es', 'it'] as const
export type SupportedLocale = (typeof supportedLocales)[number]
export const localeStorageKey = 'contestmaster.uiLocale'
type LocaleMessages = typeof en

const localeLoaders: Record<
  SupportedLocale,
  () => Promise<{ default: LocaleMessages }>
> = {
  en: async () => ({ default: en }),
  de: () => import('./locales/de.json'),
  fr: () => import('./locales/fr.json'),
  es: () => import('./locales/es.json'),
  it: () => import('./locales/it.json'),
}

export const i18n = createI18n<false, I18nOptions>({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en },
  globalInjection: false,
  warnHtmlMessage: false,
  missingWarn: import.meta.env.DEV,
  fallbackWarn: import.meta.env.DEV,
})

const loadedLocales = new Set<SupportedLocale>(['en'])
const loadingLocales = new Map<SupportedLocale, Promise<void>>()

export function isSupportedLocale(value: string): value is SupportedLocale {
  return (supportedLocales as readonly string[]).includes(value)
}

export function resolveLocale(
  browserLanguages: readonly string[],
  savedLocale?: string | null,
): SupportedLocale {
  if (savedLocale && isSupportedLocale(savedLocale)) return savedLocale
  for (const language of browserLanguages) {
    const baseLanguage = language.trim().toLowerCase().split(/[-_]/, 1)[0]
    if (baseLanguage && isSupportedLocale(baseLanguage)) return baseLanguage
  }
  return 'en'
}

export function localeMessageKey(sourceText: string): string {
  // Stable FNV-1a identifiers keep source-language sentences out of Vue I18n's
  // path syntax while retaining readable source text at call sites.
  let hash = 0x811c9dc5
  for (let index = 0; index < sourceText.length; index += 1) {
    hash ^= sourceText.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return `s_${(hash >>> 0).toString(16).padStart(8, '0')}`
}

export async function loadLocale(locale: SupportedLocale): Promise<void> {
  if (loadedLocales.has(locale)) return
  const pending = loadingLocales.get(locale)
  if (pending) return pending

  const load = localeLoaders[locale]().then(({ default: messages }) => {
    i18n.global.setLocaleMessage(locale, messages)
    loadedLocales.add(locale)
    loadingLocales.delete(locale)
  })
  loadingLocales.set(locale, load)
  try {
    await load
  } catch (error) {
    loadingLocales.delete(locale)
    throw error
  }
}

function getBrowserStorage(): Storage | undefined {
  try {
    return typeof window === 'undefined' ? undefined : window.localStorage
  } catch {
    return undefined
  }
}

export async function initializeLocale(
  browserLanguages: readonly string[] = typeof navigator === 'undefined'
    ? []
    : navigator.languages,
  storage: Storage | undefined = getBrowserStorage(),
): Promise<SupportedLocale> {
  let savedLocale: string | null = null
  try {
    savedLocale = storage?.getItem(localeStorageKey) ?? null
  } catch {
    // Browser storage can be disabled; browser language selection still works.
  }
  const locale = resolveLocale(browserLanguages, savedLocale)
  let activeLocale = locale
  try {
    await loadLocale(activeLocale)
  } catch {
    activeLocale = 'en'
  }
  i18n.global.locale.value = activeLocale
  if (typeof document !== 'undefined')
    document.documentElement.lang = activeLocale
  return activeLocale
}

export async function setLocale(
  locale: SupportedLocale,
  storage: Storage | undefined = getBrowserStorage(),
): Promise<void> {
  await loadLocale(locale)
  i18n.global.locale.value = locale
  if (typeof document !== 'undefined') document.documentElement.lang = locale
  try {
    storage?.setItem(localeStorageKey, locale)
  } catch {
    // The current page still switches languages when persistence is unavailable.
  }
}

export function translateText(
  sourceText: string,
  values?: Record<string, unknown>,
): string {
  const key = localeMessageKey(sourceText)
  const activeLocale = i18n.global.locale.value
  if (!i18n.global.te(key, activeLocale) && !i18n.global.te(key, 'en')) {
    return sourceText
  }
  return values
    ? i18n.global.t(key, values as Record<string, string | number | Date>)
    : i18n.global.t(key)
}

export function formatUtcDateTime(
  value: string | Date,
  options: Intl.DateTimeFormatOptions = {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  },
): string {
  const activeLocale = i18n.global.locale.value
  const locale = activeLocale === 'en' ? 'en-GB' : activeLocale
  return `${new Intl.DateTimeFormat(locale, { ...options, timeZone: 'UTC' }).format(new Date(value))} UTC`
}

export function formatUtcMonth(month: number): string {
  if (!Number.isInteger(month) || month < 1 || month > 12) {
    throw new RangeError('Month must be an integer from 1 through 12.')
  }
  return new Intl.DateTimeFormat(i18n.global.locale.value, {
    month: 'long',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(2000, month - 1, 1)))
}

export function formatInteger(value: number): string {
  if (!Number.isInteger(value)) {
    throw new RangeError('Localized score and count values must be integers.')
  }
  return new Intl.NumberFormat(i18n.global.locale.value, {
    maximumFractionDigits: 0,
  }).format(value)
}
