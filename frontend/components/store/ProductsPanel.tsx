"use client";

import { useState } from "react";

import { apiFetch, useApi } from "@/hooks/useApi";
import ProductForm from "@/components/store/ProductForm";

interface Product {
  id: number;
  sku: string;
  name: string;
  category: string | null;
  unit: string;
  unit_price: string;
  stock_quantity: number;
  active: boolean;
}

// Abaixo disso o estoque fica marcado em destaque -- não é uma regra de
// negócio (não existe reposição automática nem alerta real hoje), só um
// sinal visual pra quem está olhando a tabela decidir se repõe.
const LOW_STOCK_THRESHOLD = 5;

export default function ProductsPanel() {
  const { data: products, loading, error, reload } = useApi<Product[]>("/store/products");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editPrice, setEditPrice] = useState("");
  const [editStock, setEditStock] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  function startEdit(product: Product) {
    setEditingId(product.id);
    setEditPrice(product.unit_price);
    setEditStock(String(product.stock_quantity));
    setEditActive(product.active);
    setEditError(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditError(null);
  }

  async function saveEdit(productId: number) {
    setSaving(true);
    setEditError(null);
    try {
      await apiFetch(`/store/products/${productId}`, {
        method: "PATCH",
        body: JSON.stringify({
          unit_price: editPrice,
          stock_quantity: Number(editStock),
          active: editActive,
        }),
      });
      setEditingId(null);
      reload();
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Falha ao salvar produto");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <button
        className="button"
        type="button"
        onClick={() => setShowForm((v) => !v)}
        style={{ marginBottom: "1.25rem" }}
      >
        {showForm ? "Cancelar" : "Novo produto"}
      </button>

      {showForm && (
        <ProductForm
          onCreated={() => {
            setShowForm(false);
            reload();
          }}
        />
      )}

      {loading && <p className="muted">Carregando…</p>}
      {error && <p className="error">Erro: {error}</p>}
      {!loading && !error && (!products || products.length === 0) && (
        <p className="muted">Nenhum produto cadastrado.</p>
      )}

      {!loading && !error && products && products.length > 0 && (
        <div className="card">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Produto</th>
                  <th>Categoria</th>
                  <th>Unidade</th>
                  <th>Preço</th>
                  <th>Estoque</th>
                  <th>Status</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {products.map((product) => {
                  const isEditing = editingId === product.id;
                  return (
                    <tr key={product.id}>
                      <td>{product.sku}</td>
                      <td>{product.name}</td>
                      <td>{product.category ?? "—"}</td>
                      <td>{product.unit}</td>
                      <td>
                        {isEditing ? (
                          <input
                            className="input"
                            style={{ marginBottom: 0, width: "6.5rem" }}
                            type="number"
                            step="0.01"
                            min="0.01"
                            value={editPrice}
                            onChange={(event) => setEditPrice(event.target.value)}
                            aria-label={`Preço de ${product.name}`}
                          />
                        ) : (
                          `R$ ${product.unit_price}`
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <input
                            className="input"
                            style={{ marginBottom: 0, width: "5rem" }}
                            type="number"
                            min="0"
                            value={editStock}
                            onChange={(event) => setEditStock(event.target.value)}
                            aria-label={`Estoque de ${product.name}`}
                          />
                        ) : (
                          <>
                            {product.stock_quantity}
                            {product.stock_quantity <= LOW_STOCK_THRESHOLD && (
                              <span className="badge" style={{ marginLeft: "0.5rem" }}>
                                estoque baixo
                              </span>
                            )}
                          </>
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <label style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                            <input
                              type="checkbox"
                              checked={editActive}
                              onChange={(event) => setEditActive(event.target.checked)}
                              aria-label={`Ativo: ${product.name}`}
                            />
                            Ativo
                          </label>
                        ) : (
                          <span className="badge">{product.active ? "Ativo" : "Inativo"}</span>
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <div style={{ display: "flex", gap: "0.4rem" }}>
                            <button
                              className="button"
                              type="button"
                              disabled={saving}
                              onClick={() => saveEdit(product.id)}
                            >
                              {saving ? "Salvando…" : "Salvar"}
                            </button>
                            <button className="button" type="button" onClick={cancelEdit}>
                              Cancelar
                            </button>
                          </div>
                        ) : (
                          <button className="button" type="button" onClick={() => startEdit(product)}>
                            Editar
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {editError && <p className="error">{editError}</p>}
        </div>
      )}
    </>
  );
}
