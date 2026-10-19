import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "@/hooks/useApi";
import { explainError } from "@/lib/darius-api";

function respond(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch error mapping", () => {
  it("keeps a string detail as the message (previous behaviour)", async () => {
    respond(400, { detail: "Credenciais inválidas" });
    await expect(apiFetch("/x")).rejects.toMatchObject({ message: "Credenciais inválidas", status: 400 });
  });

  it("uses the message of an object detail instead of '[object Object]' and keeps the raw detail", async () => {
    const detail = { message: "DARIUS indisponível", code: "DARIUS_UNAVAILABLE", outcome_unknown: true };
    respond(502, { detail });
    const error = await apiFetch("/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("DARIUS indisponível");
    expect((error as ApiError).status).toBe(502);
    expect((error as ApiError).detail).toEqual(detail);
  });

  it("falls back to the status for validation arrays and missing detail", async () => {
    respond(422, { detail: [{ loc: ["body", "reason"], msg: "too short" }] });
    await expect(apiFetch("/x")).rejects.toMatchObject({ message: "Request failed: 422" });
    respond(500, {});
    await expect(apiFetch("/x")).rejects.toMatchObject({ message: "Request failed: 500" });
  });
});

describe("explainError", () => {
  it("maps bridge codes to an operator hint and flags an unknown outcome", async () => {
    respond(502, { detail: { message: "timeout", code: "DARIUS_UNAVAILABLE", outcome_unknown: true } });
    const explained = explainError(await apiFetch("/x").catch((e: unknown) => e));
    expect(explained.message).toBe("timeout");
    expect(explained.hint).toMatch(/inacessível/);
    expect(explained.outcomeUnknown).toBe(true);
  });

  it("explains a 409 conflict and tolerates plain errors and non-errors", async () => {
    respond(409, { detail: { message: "Task is not awaiting approval" } });
    const conflict = explainError(await apiFetch("/x").catch((e: unknown) => e));
    expect(conflict.hint).toMatch(/já mudou de estado/);
    expect(conflict.outcomeUnknown).toBe(false);
    expect(explainError(new Error("boom"))).toEqual({ message: "boom", hint: undefined, outcomeUnknown: false });
    expect(explainError("x").message).toBe("Erro desconhecido");
  });

  it("never invents a hint for an unknown code", async () => {
    respond(502, { detail: { message: "x", code: "SOMETHING_NEW" } });
    expect(explainError(await apiFetch("/x").catch((e: unknown) => e)).hint).toBeUndefined();
  });
});
