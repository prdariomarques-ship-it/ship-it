"use client";

import { MessageCircle, Inbox, Send, ListOrdered } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { MetricCard } from "@/components/admin/MetricCard";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Badge } from "@/components/admin/ui/badge";
import { useAdminWhatsApp } from "@/lib/admin-api";
import { formatNumber } from "@/lib/format";

export default function AdminWhatsAppPage() {
  const { data, isLoading, isError, error, refetch } = useAdminWhatsApp();

  return (
    <div>
      <AdminPageHeader
        title="WhatsApp"
        subtitle="Status da sessão, fila de jobs e volume de mensagens do provider configurado."
      />
      {isLoading ? (
        <LoadingGrid count={4} />
      ) : isError ? (
        <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
      ) : data ? (
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <MessageCircle className="h-4 w-4" />
                Provider: {data.provider}
              </CardTitle>
              <Badge variant={data.connected ? "success" : "destructive"}>
                {data.connected ? "Conectado" : "Desconectado"}
              </Badge>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">{data.detail}</p>
              {data.qr_page_url ? (
                <a
                  href={data.qr_page_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-block text-sm text-primary hover:underline"
                >
                  Ver QR Code / reconectar
                </a>
              ) : (
                <p className="mt-3 text-xs text-muted-foreground">
                  QR Code não disponível — configure OPENWA_PUBLIC_QR_URL para exibir o link de
                  reconexão aqui.
                </p>
              )}
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <MetricCard label="Fila (jobs)" value={formatNumber(data.queue_depth)} icon={ListOrdered} />
            <MetricCard label="Mensagens enviadas" value={formatNumber(data.messages_sent)} icon={Send} />
            <MetricCard label="Mensagens recebidas" value={formatNumber(data.messages_received)} icon={Inbox} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
