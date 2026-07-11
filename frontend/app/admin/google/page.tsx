"use client";

import { RefreshCw } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { GoogleCard } from "@/components/admin/GoogleCard";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { Button } from "@/components/admin/ui/button";
import { useAdminGoogle } from "@/lib/admin-api";
import { apiFetch } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";

// Reuses the OAuth `/connect` endpoint each domain already exposes
// (mail/gcalendar/gcontacts/gdrive routers) — this page never talks to
// Google directly and never touches the OAuth flow itself.
const CONNECT_PATH: Record<string, string> = {
  mail: "/mail/connect",
  calendar: "/gcalendar/connect",
  contacts: "/gcontacts/connect",
  drive: "/gdrive/connect",
};

export default function AdminGooglePage() {
  const { data, isLoading, isError, error, refetch } = useAdminGoogle();
  const { toast } = useToast();

  async function handleReconnect(domain: string) {
    try {
      const result = await apiFetch<{ authorization_url: string }>(CONNECT_PATH[domain]);
      window.open(result.authorization_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      toast({
        title: "Não foi possível iniciar a reconexão",
        description: err instanceof Error ? err.message : String(err),
        variant: "destructive",
      });
    }
  }

  return (
    <div>
      <AdminPageHeader
        title="Google Workspace"
        subtitle="Status de conexão OAuth por domínio (Gmail, Calendar, Contacts, Drive)."
      />
      {isLoading ? (
        <LoadingGrid count={4} />
      ) : isError ? (
        <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
      ) : data ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {(["mail", "calendar", "contacts", "drive"] as const).map((domain) => (
            <div key={domain} className="flex flex-col gap-2">
              <GoogleCard domain={data[domain]} />
              <Button variant="outline" size="sm" className="self-start" onClick={() => handleReconnect(domain)}>
                <RefreshCw className="h-3.5 w-3.5" />
                Reconnect
              </Button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
