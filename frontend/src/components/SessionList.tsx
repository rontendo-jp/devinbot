'use client';

import { useState, useEffect } from 'react';
import { config } from '@/config';

interface Session {
  id: string;
  devin_session_id: string;
  repository_id: string;
  trigger_type: string;
  status: string;
  prompt: string;
  created_at: string;
  completed_at: string | null;
}

interface SessionListProps {
  selectedRepository: string | null;
}

export default function SessionList({ selectedRepository }: SessionListProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');

  useEffect(() => {
    fetchSessions();
    const interval = setInterval(fetchSessions, config.pollIntervalMs);
    return () => clearInterval(interval);
  }, [selectedRepository, filter]);

  const fetchSessions = async () => {
    try {
      const params = new URLSearchParams();
      if (selectedRepository) params.append('repository_id', selectedRepository);
      if (filter !== 'all') params.append('status', filter);

      const response = await fetch(`${config.apiUrl}/api/sessions/?${params}`);
      if (!response.ok) throw new Error('Failed to fetch sessions');
      
      const data = await response.json();
      setSessions(data.sessions);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

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

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200">
      <div className="p-6 border-b border-gray-200">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-lg font-semibold text-gray-900">Sessions</h2>
          <div className="flex gap-2">
            {['all', 'running', 'completed', 'failed'].map((status) => (
              <button
                key={status}
                onClick={() => setFilter(status)}
                className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                  filter === status
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {status.charAt(0).toUpperCase() + status.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border-b border-red-200">
          <p className="text-red-800 text-sm">{error}</p>
        </div>
      )}

      {loading && sessions.length === 0 ? (
        <div className="p-12 text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="mt-2 text-gray-600 text-sm">Loading sessions...</p>
        </div>
      ) : sessions.length === 0 ? (
        <div className="p-12 text-center">
          <p className="text-gray-500 text-sm">No sessions found</p>
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
                      {session.status}
                    </span>
                    <span className="text-xs text-gray-500">
                      {new Date(session.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="text-sm text-gray-900 font-medium mb-1 truncate">
                    {session.prompt.substring(0, 100)}...
                  </p>
                  <div className="flex items-center gap-4 text-xs text-gray-500">
                    <span>Trigger: {session.trigger_type}</span>
                    <span>ID: {session.devin_session_id?.substring(0, 8)}...</span>
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