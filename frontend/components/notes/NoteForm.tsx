"use client";

import { FormEvent, KeyboardEvent, useState } from "react";

import { apiFetch } from "@/hooks/useApi";

interface EditableNote {
  id: number;
  title: string;
  content: string;
  tags: string[];
  pinned: boolean;
}

function tagsToInput(tags: string[]): string {
  return tags.join(", ");
}

function inputToTags(value: string): string[] {
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag.length > 0);
}

export default function NoteForm({
  note,
  onSaved,
}: {
  note?: EditableNote;
  onSaved: () => void;
}) {
  const isEditing = note !== undefined;
  const [title, setTitle] = useState(note?.title ?? "");
  const [content, setContent] = useState(note?.content ?? "");
  const [tagsInput, setTagsInput] = useState(tagsToInput(note?.tags ?? []));
  const [pinned, setPinned] = useState(note?.pinned ?? false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setTitle("");
    setContent("");
    setTagsInput("");
    setPinned(false);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const body = {
        title,
        content,
        tags: inputToTags(tagsInput),
        pinned,
      };
      if (isEditing) {
        await apiFetch(`/notes/${note.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      } else {
        await apiFetch("/notes", { method: "POST", body: JSON.stringify(body) });
        reset();
      }
      onSaved();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : `Falha ao ${isEditing ? "salvar" : "criar"} nota`
      );
    } finally {
      setSubmitting(false);
    }
  }

  // Optimizes for speed: Ctrl/Cmd+Enter submits from either field without
  // reaching for the mouse, same convention as most note/chat apps.
  function handleKeyDown(event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <form
      className="card"
      onSubmit={handleSubmit}
      aria-label={isEditing ? "Editar nota" : "Nova nota"}
    >
      <input
        className="input"
        placeholder="Título da nota"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        onKeyDown={handleKeyDown}
        autoFocus
        required
      />
      <textarea
        className="input"
        placeholder="Conteúdo (Ctrl+Enter para salvar)"
        value={content}
        onChange={(event) => setContent(event.target.value)}
        onKeyDown={handleKeyDown}
        rows={4}
      />
      <input
        className="input"
        placeholder="Tags separadas por vírgula (opcional)"
        value={tagsInput}
        onChange={(event) => setTagsInput(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.9rem" }}>
        <input
          type="checkbox"
          checked={pinned}
          onChange={(event) => setPinned(event.target.checked)}
        />
        Fixar no topo
      </label>
      {error && <p className="error">{error}</p>}
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "Salvando…" : isEditing ? "Salvar" : "Criar nota"}
      </button>
    </form>
  );
}
