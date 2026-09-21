'use client';

import { useLocale } from '@/i18n/LocaleContext';
import { Locale, locales } from '@/i18n/translations';

export default function LanguageSelector() {
  const { locale, setLocale, t } = useLocale();

  return (
    <select
      aria-label={t('app.language')}
      value={locale}
      onChange={(e) => setLocale(e.target.value as Locale)}
      className="px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      {locales.map((l) => (
        <option key={l.value} value={l.value}>
          {l.label}
        </option>
      ))}
    </select>
  );
}
