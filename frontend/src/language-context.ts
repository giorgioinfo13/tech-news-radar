import { createContext, useContext } from 'react'
import {
  type Language,
  type MessageKey,
  type MessageValues,
  type UiMessage,
  translate,
} from './messages'

export const languageStorageKey = 'tnr-language'
export function languageFrom(value: string | null): Language {
  return value === 'en' ? 'en' : 'it'
}

export const LanguageContext = createContext<{
  language: Language
  changeLanguage: (language: Language) => void
}>({ language: 'it', changeLanguage: () => {} })

export function useLanguage() {
  const context = useContext(LanguageContext)
  return {
    ...context,
    locale: context.language === 'en' ? 'en-GB' : 'it-IT',
    privacyHref: context.language === 'en' ? '/privacy.en.html' : '/privacy.html',
    t: (input: MessageKey | UiMessage, values?: MessageValues) =>
      translate(input, context.language, values),
  }
}
