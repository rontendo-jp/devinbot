import { useState, useEffect, useRef } from 'react';
import { config } from '@/config';

interface RealtimeMetrics {
  timestamp: string;
  active_sessions: number;
  recent_completed: number;
  recent_failed: number;
  active_session_details: Array<{
    id: string;
    devin_session_id: string;
    repository_name: string;
    trigger_type: string;
    created_at: string;
  }>;
}

export function useWebSocket() {
  const [metrics, setMetrics] = useState<RealtimeMetrics | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const wsUrl = config.apiUrl.replace('http', 'ws') + '/ws/ws';
    
    try {
      wsRef.current = new WebSocket(wsUrl);
      
      wsRef.current.onopen = () => {
        setConnected(true);
        setError(null);
        console.log('WebSocket connected');
      };
      
      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setMetrics(data);
        } catch (err) {
          console.error('Error parsing WebSocket message:', err);
        }
      };
      
      wsRef.current.onerror = (event) => {
        console.error('WebSocket error:', event);
        setError('WebSocket connection error');
        setConnected(false);
      };
      
      wsRef.current.onclose = () => {
        setConnected(false);
        console.log('WebSocket disconnected');
      };
      
    } catch (err) {
      setError('Failed to create WebSocket connection');
      console.error('WebSocket creation error:', err);
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return { metrics, connected, error };
}