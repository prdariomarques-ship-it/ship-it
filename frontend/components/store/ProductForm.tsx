"use client";

import { FormEvent, useState } from "react";

import { apiFetch } from "@/hooks/useApi";

export default function ProductForm({ onCreated }: { onCreated: () => void }) {
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [unit, setUnit] = useState("un");
  const [unitPrice, setUnitPrice] = useState("");
  const [stockQuantity, setStockQuantity] = useState("0");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setSku("");
    setName("");
    setCategory("");
    setUnit("un");
    setUnitPrice("");
    setStockQuantity("0");
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/store/products", {
        method: "POST",
        body: JSON.stringify({
          sku,
          name,
          category: category || null,
          unit,
          unit_price: unitPrice,
          stock_quantity: Number(stockQuantity),
        }),
      });
      reset();
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar produto");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit} aria-label="Novo produto">
      <input
        className="input"
        placeholder="SKU"
        value={sku}
        onChange={(event) => setSku(event.target.value)}
        required
      />
      <input
        className="input"
        placeholder="Nome do produto"
        value={name}
        onChange={(event) => setName(event.target.value)}
        required
      />
      <input
        className="input"
        placeholder="Categoria (opcional, ex: tinta_latex)"
        value={category}
        onChange={(event) => setCategory(event.target.value)}
      />
      <input
        className="input"
        placeholder="Unidade (ex: lata_18L, galao_3.6L, un)"
        value={unit}
        onChange={(event) => setUnit(event.target.value)}
        required
      />
      <input
        className="input"
        type="number"
        step="0.01"
        min="0.01"
        placeholder="Preço unitário"
        value={unitPrice}
        onChange={(event) => setUnitPrice(event.target.value)}
        required
      />
      <input
        className="input"
        type="number"
        min="0"
        placeholder="Estoque inicial"
        value={stockQuantity}
        onChange={(event) => setStockQuantity(event.target.value)}
        required
      />
      {error && <p className="error">{error}</p>}
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "Criando…" : "Criar produto"}
      </button>
    </form>
  );
}
