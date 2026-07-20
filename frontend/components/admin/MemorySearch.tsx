"use client";

import { FormEvent, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Badge } from "@/components/admin/ui/badge";
import { Input } from "@/components/admin/ui/input";
import { Button } from "@/components/admin/ui/button";
import { EmptyState } from "@/components/admin/EmptyState";
import { ErrorState } from "@/components/admin/ErrorState";
import { useMemorySearch } from "@/lib/admin-api";

export function MemorySearch() {
  const [input, setInput] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const { data, isFetching, isError, error, refetch } = useMemorySearch(submittedQuery);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmittedQuery(input.trim());
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Busca semântica</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <Input
            placeholder="O que você quer lembrar? (ex: contato interessado em orçamento)"
            aria-label="Busca semântica"
            value={input}
            onChange={(event) => setInput(event.target.value)}
          />
          <Button type="submit" disabled={input.trim().length === 0 || isFetching}>
            {isFetching ? "Buscando…" : "Buscar"}
          </Button>
        </form>

        {isError && (
          <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
        )}

        {!isError && submittedQuery && !isFetching && data && data.length === 0 && (
          <EmptyState
            title="Nenhum resultado"
            description="Nada na memória semântica corresponde a essa busca."
            compact
          />
        )}

        {!isError && data && data.length > 0 && (
          <div className="flex flex-col gap-2">
            {data.map((result, index) => (
              <div
                key={index}
                className="rounded-md border border-border p-3 text-sm"
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <Badge variant="secondary">{result.source}</Badge>
                  <span className="text-xs text-muted-foreground">
                    score: {result.score.toFixed(3)}
                  </span>
                </div>
                <p>{result.content}</p>
                {result.contact_id !== null && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Contato #{result.contact_id}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
