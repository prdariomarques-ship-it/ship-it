"use client";

import { LoadingRows } from "@/components/admin/LoadingGrid";
import { EmptyState } from "@/components/admin/EmptyState";
import { Badge } from "@/components/admin/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Banner, ErrorLine } from "@/components/darius/common";
import { useTelegramInventory } from "@/lib/darius-api";
import type { TelegramBot, TelegramRuntimeStatus } from "@/lib/darius-types";

type BadgeVariant = NonNullable<React.ComponentProps<typeof Badge>["variant"]>;

const STATUS_LABEL: Record<TelegramRuntimeStatus, string> = {
  ativo_evidenciado: "ativo (evidenciado)",
  sem_agendamento: "sem agendamento",
  nao_verificado: "não verificado",
  inconclusivo: "INCONCLUSIVO",
};

const STATUS_VARIANT: Record<TelegramRuntimeStatus, BadgeVariant> = {
  ativo_evidenciado: "success",
  sem_agendamento: "secondary",
  nao_verificado: "warning",
  inconclusivo: "outline",
};

const TRIGGER_LABEL = { schedule: "agendado", manual: "manual", continuous: "contínuo" } as const;

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm">{children}</dd>
    </div>
  );
}

function BotCard({ bot }: { bot: TelegramBot }) {
  const { runtime } = bot;
  return (
    <Card role="group" aria-label={bot.name}>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{bot.name}</CardTitle>
        <div className="flex items-center gap-2">
          <Badge variant="outline">{bot.scope === "ship-it" ? "neste repositório" : "repositório externo"}</Badge>
          <Badge variant={STATUS_VARIANT[runtime.status]}>{STATUS_LABEL[runtime.status]}</Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm">{bot.purpose}</p>
        <Banner tone={runtime.status === "inconclusivo" ? "warning" : "info"}>
          <p>{runtime.detail}</p>
          {runtime.evidence ? (
            <p className="mt-1 break-all text-xs text-muted-foreground">
              Evidência{runtime.as_of ? ` (${runtime.as_of})` : ""}: {runtime.evidence}
            </p>
          ) : null}
        </Banner>
        <dl className="grid gap-3 sm:grid-cols-2">
          {bot.commands.length > 0 ? (
            <Field label="Comandos">
              <span className="font-mono text-xs">{bot.commands.join(" ")}</span>
            </Field>
          ) : null}
          {bot.triggers.length > 0 ? (
            <Field label="Disparo">
              <ul className="list-disc pl-4">
                {bot.triggers.map((trigger) => (
                  <li key={`${trigger.kind}-${trigger.expression ?? trigger.host}`}>
                    {TRIGGER_LABEL[trigger.kind]}
                    {trigger.expression ? <span className="font-mono text-xs"> {trigger.expression}</span> : null}
                    {" — "}
                    {trigger.host}
                  </li>
                ))}
              </ul>
            </Field>
          ) : null}
          {bot.data_sources.length > 0 ? <Field label="Fontes de dados">{bot.data_sources.join("; ")}</Field> : null}
          {bot.credentials.length > 0 ? (
            <Field label="Credenciais (apenas nomes)">
              <span className="font-mono text-xs">{bot.credentials.join(", ")}</span>
            </Field>
          ) : null}
          {bot.source_files.length > 0 ? (
            <Field label="Código">
              <span className="break-all font-mono text-xs">{bot.source_files.join(", ")}</span>
            </Field>
          ) : null}
        </dl>
        {bot.risks.length > 0 ? (
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Riscos conhecidos</p>
            <ul className="mt-1 list-disc pl-4 text-sm">
              {bot.risks.map((risk) => (
                <li key={risk}>{risk}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/**
 * Read-only audited inventory of the Telegram bots. It is static by construction (Dario OS holds no Telegram
 * credential and does not read GitHub Actions), and says so; nothing here starts or stops a bot.
 */
export function TelegramTab() {
  const { data, isLoading, isError, error } = useTelegramInventory();

  if (isLoading) return <LoadingRows count={4} />;
  if (isError) return <ErrorLine error={error} />;
  if (!data || data.bots.length === 0) {
    return <EmptyState title="Nenhum bot inventariado" description="O inventário do Telegram está vazio." />;
  }
  const counts = Object.entries(data.counts_by_runtime_status) as Array<[TelegramRuntimeStatus, number]>;
  return (
    <div className="flex flex-col gap-4">
      <Banner tone="info">
        <p className="font-medium">Inventário auditado em {data.as_of} — não é estado em tempo real.</p>
        <p className="mt-1 text-xs">{data.live_state_note}</p>
        {!data.live_state_available ? (
          <p className="mt-1 text-xs">Estado em tempo real: indisponível.</p>
        ) : null}
      </Banner>
      <div className="flex flex-wrap gap-2" aria-label="Resumo por situação">
        {counts.map(([status, count]) => (
          <Badge key={status} variant={STATUS_VARIANT[status] ?? "outline"}>
            {STATUS_LABEL[status] ?? status}: {count}
          </Badge>
        ))}
      </div>
      {data.bots.map((bot) => (
        <BotCard key={bot.id} bot={bot} />
      ))}
    </div>
  );
}
