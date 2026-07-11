"use client";

import { Lock } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Badge } from "@/components/admin/ui/badge";
import { useAdminSystem } from "@/lib/admin-api";

function SettingRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-border py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

export default function AdminSettingsPage() {
  const { data, isLoading, isError, error, refetch } = useAdminSystem();

  return (
    <div>
      <AdminPageHeader
        title="Settings"
        subtitle="Somente leitura nesta sprint — configuração é feita via variáveis de ambiente (.env)."
        actions={
          <Badge variant="secondary" className="gap-1.5">
            <Lock className="h-3 w-3" />
            read-only
          </Badge>
        }
      />
      {isLoading ? (
        <LoadingGrid count={2} />
      ) : isError ? (
        <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
      ) : data ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Providers</CardTitle>
            </CardHeader>
            <CardContent>
              <SettingRow label="LLM" value={data.llm_provider} />
              <SettingRow label="Embeddings" value={data.embedding_provider} />
              <SettingRow label="WhatsApp" value={data.whatsapp_provider} />
              <SettingRow label="Mail (Gmail)" value={data.mail_provider} />
              <SettingRow label="Calendar" value={data.calendar_provider} />
              <SettingRow label="Contacts" value={data.contacts_provider} />
              <SettingRow label="Drive" value={data.drive_provider} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Comportamento</CardTitle>
            </CardHeader>
            <CardContent>
              <SettingRow
                label="Resposta automática (WhatsApp)"
                value={<Badge variant={data.auto_reply_enabled ? "success" : "secondary"}>{data.auto_reply_enabled ? "ativada" : "desativada"}</Badge>}
              />
              <SettingRow
                label="Fila de jobs"
                value={<Badge variant={data.jobs_enabled ? "success" : "secondary"}>{data.jobs_enabled ? "ativa" : "desativada"}</Badge>}
              />
              <SettingRow label="Ambiente" value={data.environment} />
            </CardContent>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Segredos e credenciais</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Chaves de API, tokens OAuth e segredos nunca são expostos por este dashboard — são configurados
                exclusivamente via variáveis de ambiente no arquivo <code className="rounded bg-muted px-1 py-0.5 text-xs">.env</code> do
                backend. Edição fica fora do escopo desta sprint (dashboard somente leitura).
              </p>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
