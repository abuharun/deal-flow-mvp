import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { uz, type Messages } from './uz'
import { ru } from './ru'

/**
 * Interface locale — which language the chrome, labels, and seeded content
 * render in. Deliberately separate from `Lang` (uz|ru|en): the verdict body
 * keeps its own language selector because the English original is a product
 * guarantee, not an interface preference.
 */
export type Locale = 'uz' | 'ru'

export const LOCALES: Locale[] = ['uz', 'ru']

/** Autonyms for the switcher — a language's own name never gets translated. */
export const LOCALE_NAME: Record<Locale, string> = { uz: 'O‘zbekcha', ru: 'Русский' }

/**
 * Locale preference lives under its own key, apart from the business state in
 * `oqim:v2` — switching or migrating a language never touches demo data.
 */
export const LOCALE_STORAGE_KEY = 'oqim:locale'

const DICTS: Record<Locale, Messages> = { uz, ru }

export function loadLocale(): Locale {
  try {
    return localStorage.getItem(LOCALE_STORAGE_KEY) === 'ru' ? 'ru' : 'uz'
  } catch {
    return 'uz'
  }
}

interface LocaleApi {
  locale: Locale
  setLocale: (locale: Locale) => void
  /** The active dictionary. */
  t: Messages
}

// Default value lets leaf components render (in Uzbek) without a provider,
// which keeps focused unit tests free of wrapper boilerplate.
const LocaleContext = createContext<LocaleApi>({ locale: 'uz', setLocale: () => {}, t: uz })

export function LocaleProvider({ children, initial }: { children: ReactNode; initial?: Locale }) {
  const [locale, setLocale] = useState<Locale>(initial ?? loadLocale)

  useEffect(() => {
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale)
    } catch {
      // Storage unavailable — the preference lasts for the session only.
    }
    const t = DICTS[locale]
    document.documentElement.lang = locale
    document.title = t.meta.title
    document.querySelector('meta[name="description"]')?.setAttribute('content', t.meta.description)
  }, [locale])

  const api = useMemo<LocaleApi>(() => ({ locale, setLocale, t: DICTS[locale] }), [locale])
  return <LocaleContext.Provider value={api}>{children}</LocaleContext.Provider>
}

export function useLocale(): LocaleApi {
  return useContext(LocaleContext)
}
