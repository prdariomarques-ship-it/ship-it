import { CheckCircle2, XCircle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Badge } from "@/components/admin/ui/badge";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { GoogleDomainStatus } from "@/lib/admin-types";

const DOMAIN_LABEL: Record<string, string> = {
  mail: "Gmail",
  calendar: "Google Calendar",
  contacts: "Google Contacts",
  drive: "Google Drive",
};

export function GoogleCard({ domain }: { domain: GoogleDomainStatus }) {
  const connected = domain.connected_accounts > 0;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle>{DOMAIN_LABEL[domain.domain] ?? domain.domain}</CardTitle>
        {connected ? (
          <CheckCircle2 className="h-4 w-4 text-success" />
        ) : (
          <XCircle className="h-4 w-4 text-muted-foreground" />
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Contas conectadas</span>
          <span className="font-medium">{domain.connected_accounts}</span>
        </div>
        {domain.indexed_items !== null ? (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Itens indexados</span>
            <span className="font-medium">{formatNumber(domain.indexed_items)}</span>
          </div>
        ) : null}
        {domain.last_indexed_at !== null ? (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Última sincronização</span>
            <span className="font-medium">{formatDateTime(domain.last_indexed_at)}</span>
          </div>
        ) : (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Última sincronização</span>
            <span className="text-xs text-muted-foreground">não disponível</span>
          </div>
        )}
        {domain.accounts.length > 0 ? (
          <div className="mt-1 flex flex-wrap gap-1.5">
            {domain.accounts.map((account) => (
              <Badge key={account.user_id} variant="secondary">
                {account.label}
              </Badge>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">Nenhuma conta conectada.</p>
        )}
      </CardContent>
    </Card>
  );
}
