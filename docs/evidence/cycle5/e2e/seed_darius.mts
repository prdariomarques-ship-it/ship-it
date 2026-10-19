// Seeds an ISOLATED, throw-away DARIUS SQLite file for the panel validation. Never points at a real DB.
import { randomUUID } from "node:crypto";
import fs from "node:fs";

import { SQLitePersistentStore } from "file:///C:/Users/dario/Downloads/darius-rc2-prepush-gate/src/core/sqlite.ts";

const dbPath = process.argv[2];
if (!dbPath || !/[\\/]e2e[\\/]run[\\/]/.test(dbPath)) throw new Error("refusing to seed outside the e2e run directory: " + dbPath);
if (fs.existsSync(dbPath)) throw new Error("seed target must not exist yet");

const store = new SQLitePersistentStore(dbPath);
const now = Date.now();
const mk = (objective: string, status: string, minutesAgo: number, extra: Record<string, unknown> = {}) =>
  store.saveTask({
    id: randomUUID(), objective, status, agentId: "agent-1", ownerId: "svc",
    createdAt: new Date(now - minutesAgo * 60_000), updatedAt: new Date(now - (minutesAgo - 1) * 60_000), ...extra,
  } as never);

mk("Enviar contrato revisado ao cliente", "PAUSED", 5);
mk("Responder ao cliente sobre a reunião de quinta", "PAUSED", 12);
mk("Cobrar fatura em atraso (efeito desconhecido)", "FAILED", 30, {
  error: "ACT timed out", metadata: { failureClass: "EFFECT_UNKNOWN" },
});
mk("Consultar cotação (tentativas esgotadas)", "FAILED", 45, {
  error: "provider 503", metadata: { failureClass: "RETRIES_EXHAUSTED" },
});
mk("Resumo diário em espera para nova tentativa", "QUEUED", 8, {
  metadata: { queueRetry: { attempts: 2, nextAttemptAt: now + 3_600_000, lastError: "provider 503" } },
});
mk("Gerar relatório semanal", "COMPLETED", 90, { result: "Relatório gerado: 3 páginas." });
mk("Tarefa em execução simulada", "RUNNING", 2);
for (let i = 0; i < 30; i++) mk(`Tarefa concluída de exemplo ${i + 1}`, "COMPLETED", 120 + i, { result: "ok" });
console.log("seeded darius:", dbPath);
