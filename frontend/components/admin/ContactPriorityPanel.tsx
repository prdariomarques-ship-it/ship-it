import Link from "next/link";

import { Badge } from "@/components/admin/ui/badge";
import { EmptyState } from "@/components/admin/EmptyState";
import { formatRelativeTime } from "@/lib/format";
import type { ContactPriorityItem, RelationshipTier } from "@/lib/admin-types";

// Pure visualization layer over the deterministic Contact Intelligence
// ranking (GET /contacts/priority) -- no scoring here, see
// contacts/intelligence.py. Answers one question only: "who should I work
// on next?" — never duplicates contact detail (that's the Contact
// Workspace's job, linked to below) and never executes anything (that's
// P0-4's job, on the Contact Workspace page).
const TIER_TONE: Record<RelationshipTier, "secondary" | "success" | "warning" | "destructive"> = {
  healthy: "success",
  cooling: "secondary",
  cold: "warning",
  at_risk: "destructive",
};

const TIER_LABEL: Record<RelationshipTier, string> = {
  healthy: "Saudável",
  cooling: "Esfriando",
  cold: "Fria",
  at_risk: "Em risco",
};

export function ContactPriorityPanel({ contacts }: { contacts: ContactPriorityItem[] }) {
  if (contacts.length === 0) {
    return (
      <EmptyState
        title="Nenhum contato precisa de atenção"
        description="Nenhum sinal de risco no momento — tudo em dia."
      />
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {contacts.map((item) => (
        <li key={item.contact_id}>
          <Link
            href={`/contatos/${item.contact_id}`}
            className="block rounded-md border border-border bg-card p-3 transition-colors hover:border-primary/40"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">{item.name}</span>
              <Badge variant={TIER_TONE[item.relationship_status.tier]}>
                {TIER_LABEL[item.relationship_status.tier]}
              </Badge>
              <span className="text-xs text-muted-foreground">
                score {item.relationship_status.score}
              </span>
            </div>
            {item.primary_reason ? (
              <p className="mt-1 text-xs text-muted-foreground">{item.primary_reason}</p>
            ) : null}
            <p className="mt-1 text-xs text-foreground">{item.suggested_next_action}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Última interação: {formatRelativeTime(item.last_interaction_at)}
            </p>
          </Link>
        </li>
      ))}
    </ul>
  );
}
