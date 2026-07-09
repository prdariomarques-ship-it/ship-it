export default function StatCard({
  label,
  value,
}: {
  label: string;
  value: number | string;
}) {
  return (
    <div className="stat-card">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}
