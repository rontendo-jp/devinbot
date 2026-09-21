'use client';

import { createContext, useContext, useEffect, useSyncExternalStore, ReactNode } from 'react';
import { Locale, TranslationKey, translations } from './translations';

const STORAGE_KEY = 'devinbot.locale';
const DEFAULT_LOCALE: Locale = 'en';

const listeners = new Set<() => void>();
let currentLocale: Locale | null = null;

function isLocale(value: string | null): value is Locale {
  return value === 'en' || value === 'ja';
}

function detectLocale(): Locale {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (isLocale(stored)) return stored;
  return window.navigator.language.toLowerCase().startsWith('ja') ? 'ja' : DEFAULT_LOCALE;
}

function getSnapshot(): Locale {
  if (currentLocale === null) currentLocale = detectLocale();
  return currentLocale;
}

function getServerSnapshot(): Locale {
  return DEFAULT_LOCALE;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function setLocale(next: Locale) {
  currentLocale = next;
  window.localStorage.setItem(STORAGE_KEY, next);
  listeners.forEach((listener) => listener());
}

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey) => string;
}

const LocaleContext = createContext<LocaleContextValue>({
  locale: DEFAULT_LOCALE,
  setLocale: () => {},
  t: (key) => translations[DEFAULT_LOCALE][key],
});

export function LocaleProvider({ children }: { children: ReactNode }) {
  const locale = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const t = (key: TranslationKey) => translations[locale][key] ?? translations[DEFAULT_LOCALE][key];

  return (
    <LocaleContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale() {
  return useContext(LocaleContext);
}
