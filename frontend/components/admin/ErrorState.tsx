import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/admin/ui/button";

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <AlertTriangle className="h-8 w-8 text-destructive" />
      <p className="text-sm font-medium text-foreground">Não foi possível carregar os dados</p>
      <p className="max-w-sm text-xs text-muted-foreground">{message}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-2">
          Tentar novamente
        </Button>
      ) : null}
    </div>
  );
}
