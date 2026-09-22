'use client';

import { useState } from 'react';
import { config } from '@/config';
import { useLocale } from '@/i18n/LocaleContext';
import { TranslationKey, translations } from '@/i18n/translations';
import { usePolling } from '@/hooks/usePolling';

interface Session {
  id: string;
  devin_session_id: string | null;
  session_url: string | null;
  repository_id: string;
  trigger_type: string;
  status: string;
  devin_status: string | null;
  devin_status_detail: string | null;
  last_devin_message: string | null;
  prompt: string;
  created_at: string;
  completed_at: string | null;
}

interface SessionListProps {
  selectedRepository: string | null;
}

const FILTERS = ['all', 'running', 'completed', 'failed'] as const;

const URL_PATTERN = /(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/g;

// Timestamps without an offset are UTC; parse them as such so they render in the viewer's local time.
function parseTimestamp(value: string): Date {
  return new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`);
}

function formatLocalTime(value: string, locale: string): string {
  return parseTimestamp(value).toLocaleString(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  });
}

function linkify(text: string) {
  return text.split(URL_PATTERN).map((part, i) =>
    i % 2 === 1 ? (
      <a
        key={i}
        href={part}
        target="_blank"
        rel="noopener noreferrer"
        className="text-blue-600 hover:underline break-all"
      >
        {part}
      </a>
    ) : (
      part
    ),
  );
}

export default function SessionList({ selectedRepository }: SessionListProps) {
  const { locale, t } = useLocale();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<TranslationKey | null>(null);
  const [filter, setFilter] = useState<string>('all');

  const hasActiveSessions = sessions.some(
    (s) => s.status === 'running' || s.status === 'pending',
  );

  usePolling(
    async (signal, isInitial) => {
      try {
        if (isInitial) setLoading(true);
        const params = new URLSearchParams();
        if (selectedRepository) params.append('repository_id', selectedRepository);
        if (filter !== 'all') params.append('status', filter);

        const response = await fetch(`${config.apiUrl}/api/sessions/?${params}`, { signal });
        if (!response.ok) throw new Error('Failed to fetch sessions');

        const data = await response.json();
        setSessions(data.sessions);
        setError(null);
      } catch (err) {
        if (signal.aborted) return;
        console.error('Error fetching sessions:', err);
        setError('sessions.fetchFailed');
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    hasActiveSessions ? config.activePollIntervalMs : config.idlePollIntervalMs,
    [selectedRepository, filter],
  );

  const getStatusColor = (status: string) => {
    const colors = {
      pending: 'bg-yellow-100 text-yellow-800',
      running: 'bg-blue-100 text-blue-800',
      completed: 'bg-green-100 text-green-800',
      failed: 'bg-red-100 text-red-800',
      cancelled: 'bg-gray-100 text-gray-800',
    };
    return colors[status as keyof typeof colors] || 'bg-gray-100 text-gray-800';
  };

  const getStatusIcon = (status: string) => {
    const icons = {
      pending: '⏳',
      running: '🔄',
      completed: '✅',
      failed: '❌',
      cancelled: '🛑',
    };
    return icons[status as keyof typeof icons] || '❓';
  };

  const getStatusLabel = (status: string) => {
    const key = `status.${status}` as TranslationKey;
    return key in translations.en ? t(key) : status;
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200">
      <div className="p-6 border-b border-gray-200">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-lg font-semibold text-gray-900">{t('sessions.title')}</h2>
          <div className="flex gap-2">
            {FILTERS.map((status) => (
              <button
                key={status}
                onClick={() => setFilter(status)}
                className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                  filter === status
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {t(`filter.${status}`)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border-b border-red-200">
          <p className="text-red-800 text-sm">{t(error)}</p>
        </div>
      )}

      {loading ? (
        <div className="p-12 text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="mt-2 text-gray-600 text-sm">{t('sessions.loading')}</p>
        </div>
      ) : sessions.length === 0 ? (
        <div className="p-12 text-center">
          <p className="text-gray-500 text-sm">{t('sessions.empty')}</p>
        </div>
      ) : (
        <div className="divide-y divide-gray-200">
          {sessions.map((session) => (
            <div key={session.id} className="p-4 hover:bg-gray-50 transition-colors">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">{getStatusIcon(session.status)}</span>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(session.status)}`}>
                      {getStatusLabel(session.status)}
                    </span>
                    {session.devin_status && (
                      <span
                        className={`px-2 py-1 rounded-full text-xs font-medium ${
                          ['waiting_for_user', 'waiting_for_approval'].includes(session.devin_status_detail ?? '')
                            ? 'bg-orange-100 text-orange-800'
                            : 'bg-gray-100 text-gray-700'
                        }`}
                        title="Status reported by Devin"
                      >
                        {session.devin_status}
                        {session.devin_status_detail ? ` / ${session.devin_status_detail}` : ''}
                      </span>
                    )}
                    <span className="text-xs text-gray-500">
                      {formatLocalTime(session.created_at, locale)}
                    </span>
                  </div>
                  <p className="text-sm text-gray-900 font-medium mb-1 truncate" title={session.prompt}>
                    {session.prompt.length > 100 ? `${session.prompt.substring(0, 100)}...` : session.prompt}
                  </p>
                  {session.last_devin_message && (
                    <div className="mb-2 rounded-md bg-gray-50 border border-gray-200 p-3">
                      <p className="text-xs font-medium text-gray-500 mb-1">{t('sessions.devinSays')}</p>
                      <p className="text-sm text-gray-800 whitespace-pre-wrap break-words">
                        {linkify(session.last_devin_message)}
                      </p>
                    </div>
                  )}
                  <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500">
                    <span>{t('sessions.trigger')}: {session.trigger_type}</span>
                    {session.session_url && (
                      <a
                        href={session.session_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline"
                        title={session.devin_session_id ?? undefined}
                      >
                        {t('sessions.openInDevin')} ↗
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}