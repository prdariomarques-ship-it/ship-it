"use client";

import { Fragment, useEffect, useState } from "react";

import PageHeader from "@/components/PageHeader";
import NoteForm from "@/components/notes/NoteForm";
import { apiFetch, useApi } from "@/hooks/useApi";

interface Note {
  id: number;
  title: string;
  content: string;
  tags: string[];
  pinned: boolean;
  archived: boolean;
}

export default function NotasPage() {
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);

  // Debounced live search: waits 250ms after the last keystroke before
  // hitting the API, so typing doesn't fire a request per character.
  useEffect(() => {
    const timeout = setTimeout(() => setQuery(searchInput), 250);
    return () => clearTimeout(timeout);
  }, [searchInput]);

  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (showArchived) params.set("include_archived", "true");
  const path = `/notes${params.toString() ? `?${params.toString()}` : ""}`;

  const { data: notes, loading, error, reload } = useApi<Note[]>(path);

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleDelete(noteId: number) {
    setDeletingId(noteId);
    setDeleteError(null);
    try {
      await apiFetch(`/notes/${noteId}`, { method: "DELETE" });
      reload();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Falha ao apagar nota");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <>
      <PageHeader title="Notas" subtitle="Anotações rápidas, com tags e busca." />

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
        <button className="button" type="button" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancelar" : "Nova nota"}
        </button>
        <input
          className="input"
          placeholder="Buscar por título, conteúdo ou tag…"
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          style={{ flex: 1, minWidth: "200px", marginBottom: 0 }}
          aria-label="Buscar notas"
        />
        <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", whiteSpace: "nowrap" }}>
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(event) => setShowArchived(event.target.checked)}
          />
          Mostrar arquivadas
        </label>
      </div>

      {showForm && (
        <NoteForm
          onSaved={() => {
            setShowForm(false);
            reload();
          }}
        />
      )}

      {deleteError && <p className="error">{deleteError}</p>}

      {loading && <p className="muted">Carregando…</p>}
      {error && <p className="error">Erro: {error}</p>}
      {!loading && !error && (!notes || notes.length === 0) && (
        <p className="muted">
          {query ? "Nenhuma nota encontrada para essa busca." : "Nenhuma nota cadastrada."}
        </p>
      )}

      {!loading && !error && notes && notes.length > 0 && (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Título</th>
                <th>Conteúdo</th>
                <th>Tags</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {notes.map((note) => (
                <Fragment key={note.id}>
                  <tr>
                    <td>
                      {note.pinned && <span aria-label="Fixada">📌 </span>}
                      {note.title}
                      {note.archived && <span className="badge" style={{ marginLeft: "0.5rem" }}>arquivada</span>}
                    </td>
                    <td>{note.content}</td>
                    <td>
                      {note.tags.length > 0 ? (
                        note.tags.map((tag) => (
                          <span key={tag} className="badge" style={{ marginRight: "0.25rem" }}>
                            {tag}
                          </span>
                        ))
                      ) : (
                        "—"
                      )}
                    </td>
                    <td style={{ display: "flex", gap: "0.5rem" }}>
                      <button
                        className="button"
                        type="button"
                        onClick={() =>
                          setEditingId((current) => (current === note.id ? null : note.id))
                        }
                      >
                        {editingId === note.id ? "Fechar" : "Editar"}
                      </button>
                      <button
                        className="button"
                        type="button"
                        disabled={deletingId === note.id}
                        onClick={() => handleDelete(note.id)}
                      >
                        {deletingId === note.id ? "Apagando…" : "Apagar"}
                      </button>
                    </td>
                  </tr>
                  {editingId === note.id && (
                    <tr>
                      <td colSpan={4}>
                        <NoteForm
                          note={note}
                          onSaved={() => {
                            setEditingId(null);
                            reload();
                          }}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
