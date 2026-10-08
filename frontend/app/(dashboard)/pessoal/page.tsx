import PageHeader from "@/components/PageHeader";

// Área Pessoal — Gêmeo Darius e Conversas pessoais ficam deliberadamente
// SEM link e sem chamada de API nesta página. Motivo registrado em
// DARIUS_OS_FRONTEND_STATUS.md / INTEGRATION_STATUS.md:
//   - Não existe rota dedicada para o Gêmeo Darius neste frontend.
//   - GET /messages aceita contact_id, mas não filtra por usuário/instância
//     — exibir a listagem genérica como "conversa pessoal" seria mostrar
//     mensagens sem garantia de que pertencem ao contexto certo.
// Essa proteção só pode ser removida quando existir um contrato de
// leitura que filtre por usuário/instância E uma rota de frontend
// confirmada — não é uma decisão para esta entrega visual tomar sozinha.
export default function PessoalPage() {
  return (
    <>
      <PageHeader
        title="Pessoal"
        subtitle="Espaço próprio para o Gêmeo Darius e conversas pessoais, separado dos demais módulos."
      />

      <div className="card">
        <h2 className="page-title" style={{ fontSize: "1rem" }}>
          Gêmeo Darius
        </h2>
        <div className="empty-state" style={{ marginTop: "0.6rem" }}>
          <span className="badge" style={{ flexShrink: 0 }}>
            Indisponível
          </span>
          <div>
            <strong>Rota dedicada não encontrada</strong>
            Nenhuma sessão foi aberta nem memória foi lida. Esta área só pode ser
            ligada quando existir uma rota própria, usando a autenticação e as
            permissões já existentes no app — não é criada automaticamente aqui.
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="page-title" style={{ fontSize: "1rem" }}>
          Conversas pessoais
        </h2>
        <div className="empty-state" style={{ marginTop: "0.6rem" }}>
          <span className="badge" style={{ flexShrink: 0 }}>
            Indisponível
          </span>
          <div>
            <strong>Filtro pessoal não comprovado</strong>
            A listagem geral de mensagens (<code>/messages</code>) não filtra por
            usuário ou instância — mostrá-la aqui como &ldquo;pessoal&rdquo;
            arriscaria exibir conversas de outro contexto. Esta área fica
            desativada até existir um contrato de leitura que comprove esse
            filtro.
          </div>
        </div>
      </div>
    </>
  );
}
