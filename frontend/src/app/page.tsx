'use client';

import { useState } from 'react';
import MetricsCard from '@/components/MetricsCard';
import SessionList from '@/components/SessionList';
import RepositorySelector from '@/components/RepositorySelector';
import LanguageSelector from '@/components/LanguageSelector';
import { useLocale } from '@/i18n/LocaleContext';
import { TranslationKey } from '@/i18n/translations';
import { config } from '@/config';
import { useWebSocket } from '@/hooks/useWebSocket';
import { usePolling } from '@/hooks/usePolling';

const TIME_RANGES = ['1h', '24h', '7d', '30d', 'custom'] as const;

// Format a Date as the local-time string expected by <input type="datetime-local">.
function toLocalInputValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function defaultCustomRange() {
  const to = new Date();
  const from = new Date(to.getTime() - 60 * 60 * 1000);
  return { from: toLocalInputValue(from), to: toLocalInputValue(to) };
}

export default function Home() {
  const { t } = useLocale();
  const [selectedRepository, setSelectedRepository] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState<(typeof TIME_RANGES)[number]>('24h');
  const [customRange, setCustomRange] = useState(defaultCustomRange);
  const customRangeInvalid =
    timeRange === 'custom' &&
    !!customRange.from &&
    !!customRange.to &&
    new Date(customRange.from) >= new Date(customRange.to);
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<TranslationKey | null>(null);
  
  const { metrics: realtimeMetrics, connected: wsConnected, error: wsError } = useWebSocket();

  usePolling(
    async (signal, isInitial) => {
      try {
        if (isInitial) setLoading(true);
        const params = new URLSearchParams();
        if (selectedRepository) params.append('repository_id', selectedRepository);
        params.append('time_range', timeRange);
        if (timeRange === 'custom') {
          if (customRangeInvalid) {
            setError('timeRange.invalidRange');
            return;
          }
          if (customRange.from) params.append('start_time', new Date(customRange.from).toISOString());
          if (customRange.to) params.append('end_time', new Date(customRange.to).toISOString());
        }

        const response = await fetch(`${config.apiUrl}/api/metrics/?${params}`, { signal });
        if (!response.ok) throw new Error('Failed to fetch metrics');

        const data = await response.json();
        setMetrics(data);
        setError(null);
      } catch (err) {
        if (signal.aborted) return;
        console.error('Error fetching metrics:', err);
        setError('app.fetchMetricsFailed');
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    config.metricsPollIntervalMs,
    [selectedRepository, timeRange, customRange.from, customRange.to],
  );

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-gray-900 break-words">{t('app.title')}</h1>
            <p className="text-gray-600">{t('app.subtitle')}</p>
          </div>
          <div className="flex items-center gap-4">
            <LanguageSelector />
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
              <span className="text-sm text-gray-600 whitespace-nowrap">
                {wsConnected ? t('app.live') : t('app.offline')}
              </span>
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="mb-6 flex flex-wrap gap-4">
          <RepositorySelector
            selectedRepository={selectedRepository}
            onSelectRepository={setSelectedRepository}
          />
          
          <div className="flex flex-wrap gap-2">
            {TIME_RANGES.map((range) => (
              <button
                key={range}
                onClick={() => {
                  if (range === 'custom') setCustomRange(defaultCustomRange());
                  setTimeRange(range);
                }}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  timeRange === range
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-gray-700 hover:bg-gray-100'
                }`}
              >
                {t(`timeRange.${range}` as TranslationKey)}
              </button>
            ))}
          </div>

          {timeRange === 'custom' && (
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-sm text-gray-700">
                {t('timeRange.from')}
                <input
                  type="datetime-local"
                  value={customRange.from}
                  max={customRange.to || undefined}
                  onChange={(e) => setCustomRange((r) => ({ ...r, from: e.target.value }))}
                  className="px-3 py-2 rounded-lg bg-white text-gray-900 text-sm border border-gray-200"
                />
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700">
                {t('timeRange.to')}
                <input
                  type="datetime-local"
                  value={customRange.to}
                  min={customRange.from || undefined}
                  onChange={(e) => setCustomRange((r) => ({ ...r, to: e.target.value }))}
                  className="px-3 py-2 rounded-lg bg-white text-gray-900 text-sm border border-gray-200"
                />
              </label>
            </div>
          )}
        </div>

        {/* Error State */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-red-800">{t(error)}</p>
          </div>
        )}

        {/* Loading State */}
        {loading && !metrics && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="mt-2 text-gray-600">{t('app.loadingMetrics')}</p>
          </div>
        )}

        {/* Metrics Grid */}
        {metrics && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <MetricsCard
              title={t('metrics.totalSessions')}
              value={metrics.session_metrics.total_sessions}
              trend="+12%"
              positive
            />
            <MetricsCard
              title={t('metrics.activeSessions')}
              value={realtimeMetrics?.active_sessions || metrics.session_metrics.active_sessions}
              trend="+2"
              positive
            />
            <MetricsCard
              title={t('metrics.successRate')}
              value={`${metrics.session_metrics.success_rate}%`}
              trend="+5%"
              positive
            />
            <MetricsCard
              title={t('metrics.cost')}
              value={
                metrics.cost_metrics.total_acus == null
                  ? t('metrics.costUnavailable')
                  : !metrics.cost_metrics.data_points
                    ? t('metrics.costEnterpriseOnly')
                    : Number(metrics.cost_metrics.total_acus).toFixed(2)
              }
              muted={metrics.cost_metrics.total_acus != null && !metrics.cost_metrics.data_points}
              error={metrics.cost_metrics.error}
              subtitle={
                metrics.cost_metrics.total_acus == null
                  ? undefined
                  : !metrics.cost_metrics.data_points
                    ? t('metrics.costEnterpriseHint')
                    : `${t('metrics.costDaily')} · ${t('metrics.costDays').replace(
                        '{count}',
                        String(metrics.cost_metrics.data_points ?? 0),
                      )}`
              }
            />
          </div>
        )}

        {/* Session List */}
        <SessionList
          selectedRepository={selectedRepository}
        />
      </div>
    </div>
  );
}