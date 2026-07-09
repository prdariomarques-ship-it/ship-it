export default function PageHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <header>
      <h1 className="page-title">{title}</h1>
      {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
    </header>
  );
}
