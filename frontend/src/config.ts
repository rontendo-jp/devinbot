export const config = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  // Session list: fast while something is pending/running, slow otherwise.
  activePollIntervalMs: 5000,
  idlePollIntervalMs: 30000,
  // Metrics hit the Devin consumption API upstream, so keep this conservative.
  metricsPollIntervalMs: 30000,
};
