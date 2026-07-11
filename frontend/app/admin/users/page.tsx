"use client";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { EmptyState } from "@/components/admin/EmptyState";
import { Badge } from "@/components/admin/ui/badge";
import { Card, CardContent } from "@/components/admin/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/admin/ui/table";
import { useAdminUsers } from "@/lib/admin-api";
import { formatDateTime } from "@/lib/format";

export default function AdminUsersPage() {
  const { data, isLoading, isError, error, refetch } = useAdminUsers();

  return (
    <div>
      <AdminPageHeader title="Users" subtitle="Usuários do Dario OS — somente leitura." />
      <Card>
        <CardContent className="pt-4">
          {isLoading ? (
            <LoadingRows count={6} />
          ) : isError ? (
            <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
          ) : !data || data.length === 0 ? (
            <EmptyState title="Nenhum usuário encontrado" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>E-mail</TableHead>
                  <TableHead>Papel</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Criado em</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell className="font-medium">{user.full_name}</TableCell>
                    <TableCell className="text-muted-foreground">{user.email}</TableCell>
                    <TableCell>
                      <Badge variant={user.role === "admin" ? "default" : "secondary"}>{user.role}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={user.is_active ? "success" : "destructive"}>
                        {user.is_active ? "ativo" : "inativo"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(user.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
