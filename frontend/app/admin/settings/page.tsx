"use client";

import { Lock } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Badge } from "@/components/admin/ui/badge";
import { Switch } from "@/components/admin/ui/switch";
import { useAdminSettings, useAdminSystem, updateAdminSetting } from "@/lib/admin-api";
import { useToast } from "@/hooks/use-toast";
import type { SettingInfo } from "@/lib/admin-types";

function SettingRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-border py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function BehaviorSettingRow({
  setting,
  onToggle,
  isPending,
}: {
  setting: SettingInfo;
  onToggle: (key: string, value: boolean) => void;
  isPending: boolean;
}) {
  const isBoolean = typeof setting.value === "boolean";
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border py-3 text-sm last:border-0">
      <div>
        <p className="font-medium">{setting.description}</p>
        {!setting.editable && (
          <p className="mt-0.5 text-xs text-muted-foreground">
            Somente leitura — ver detalhes no ROADMAP.
          </p>
        )}
      </div>
      {setting.editable && isBoolean ? (
        <Switch
          checked={setting.value as boolean}
          onCheckedChange={(checked) => onToggle(setting.key, checked)}
          disabled={isPending}
          aria-label={setting.key}
        />
      ) : isBoolean ? (
        <Badge variant={setting.value ? "success" : "secondary"}>
          {setting.value ? "ativado" : "desativado"}
        </Badge>
      ) : (
        <Badge variant="outline">{String(setting.value)}</Badge>
      )}
    </div>
  );
}

export default function AdminSettingsPage() {
  const { data: system, isLoading: systemLoading, isError: systemIsError, error: systemError, refetch: refetchSystem } = useAdminSystem();
  const { data: settings, isLoading: settingsLoading, isError: settingsIsError, error: settingsError, refetch: refetchSettings } = useAdminSettings();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const updateSetting = useMutation({
    mutationFn: ({ key, value }: { key: string; value: boolean }) =>
      updateAdminSetting(key, value),
    onSuccess: () => {
      toast({ title: "Configuração atualizada", variant: "success" });
      queryClient.invalidateQueries({ queryKey: ["admin", "settings"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "system"] });
    },
    onError: (error: Error) =>
      toast({
        title: "Falha ao atualizar configuração",
        description: error.message,
        variant: "destructive",
      }),
  });

  const isLoading = systemLoading || settingsLoading;
  const isError = systemIsError || settingsIsError;

  return (
    <div>
      <AdminPageHeader
        title="Settings"
        subtitle="Providers e identidade do processo são somente leitura (variáveis de ambiente). Alguns comportamentos abaixo já podem ser editados aqui, com efeito imediato."
        actions={
          <Badge variant="secondary" className="gap-1.5">
            <Lock className="h-3 w-3" />
            providers read-only
          </Badge>
        }
      />
      {isLoading ? (
        <LoadingGrid count={2} />
      ) : isError ? (
        <ErrorState
          message={((systemError ?? settingsError) as Error).message}
          onRetry={() => {
            refetchSystem();
            refetchSettings();
          }}
        />
      ) : system && settings ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Providers</CardTitle>
            </CardHeader>
            <CardContent>
              <SettingRow label="LLM" value={system.llm_provider} />
              <SettingRow label="Embeddings" value={system.embedding_provider} />
              <SettingRow label="WhatsApp" value={system.whatsapp_provider} />
              <SettingRow label="Mail (Gmail)" value={system.mail_provider} />
              <SettingRow label="Calendar" value={system.calendar_provider} />
              <SettingRow label="Contacts" value={system.contacts_provider} />
              <SettingRow label="Drive" value={system.drive_provider} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Comportamento</CardTitle>
            </CardHeader>
            <CardContent>
              {settings.map((setting) => (
                <BehaviorSettingRow
                  key={setting.key}
                  setting={setting}
                  isPending={updateSetting.isPending}
                  onToggle={(key, value) => updateSetting.mutate({ key, value })}
                />
              ))}
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
                backend. Trocar o provider em si (não só ligar/desligar um comportamento) também continua exigindo
                variável de ambiente + reinício, já que cada provider mantém conexões/clients próprios em memória.
              </p>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
