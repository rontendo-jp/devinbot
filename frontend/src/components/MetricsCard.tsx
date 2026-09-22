interface MetricsCardProps {
  title: string;
  value: string | number;
  trend?: string;
  positive?: boolean;
  subtitle?: string;
  error?: string;
}

export default function MetricsCard({ title, value, trend, positive, subtitle, error }: MetricsCardProps) {
  return (
    <div className="bg-white rounded-lg shadow-sm p-6 border border-gray-200">
      <h3 className="text-sm font-medium text-gray-600 mb-2">{title}</h3>
      <div className="flex items-baseline justify-between">
        <p className={`text-3xl font-bold ${error ? 'text-gray-400' : 'text-gray-900'}`}>{value}</p>
        {trend && !error && (
          <span className={`text-sm font-medium ${positive ? 'text-green-600' : 'text-red-600'}`}>
            {trend}
          </span>
        )}
      </div>
      {error ? (
        <p className="mt-2 text-xs text-red-600 break-words" title={error}>{error}</p>
      ) : subtitle ? (
        <p className="mt-2 text-xs text-gray-500">{subtitle}</p>
      ) : null}
    </div>
  );
}