import { Inbox, type LucideIcon } from "lucide-react";

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: LucideIcon;
  compact?: boolean;
}

export function EmptyState({ title, description, icon: Icon = Inbox, compact = false }: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center gap-2 text-center ${compact ? "py-4" : "py-12"}`}>
      <Icon className={compact ? "h-5 w-5 text-muted-foreground" : "h-8 w-8 text-muted-foreground"} />
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description ? <p className="max-w-sm text-xs text-muted-foreground">{description}</p> : null}
    </div>
  );
}
