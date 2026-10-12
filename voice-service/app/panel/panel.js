"use strict";
// Painel do voice-service. O token fica só em memória desta aba; todo texto vindo do serviço entra como texto puro (textContent), nunca como HTML.
(function () {
  let token = "";
  let timer = null;
  const $ = (id) => document.getElementById(id);

  function api(path, options) {
    const opts = Object.assign({ headers: {} }, options || {});
    opts.headers = Object.assign({ Authorization: "Bearer " + token }, opts.headers);
    return fetch(path, opts);
  }
  function fill(dl, pairs) {
    dl.replaceChildren();
    for (const [k, v] of pairs) {
      const dt = document.createElement("dt"); dt.textContent = k;
      const dd = document.createElement("dd"); dd.textContent = String(v);
      dl.append(dt, dd);
    }
  }
  function render(st) {
    $("panel").hidden = false;
    const banner = $("modeBanner");
    banner.className = "banner " + (st.mode === "simulado" ? "sim" : (st.real_voice_possible ? "real" : "bad"));
    banner.textContent = st.mode === "simulado"
      ? "MOTOR SIMULADO: o áudio gerado aqui é um sinal de teste. Não é a sua voz. Serve só para verificar painel, fila e formato."
      : (st.real_voice_possible
        ? "Motor real carregado com perfil autorizado. Escute as amostras antes de aprovar o uso: a aprovação é humana."
        : "Motor real configurado, mas ainda não está pronto: " + (st.not_ready_reason || st.profile_error || "veja o checklist"));
    fill($("state"), [
      ["Agente", st.agent], ["Motor", st.engine], ["Modelo", st.model_id || "—"], ["Revisão dos pesos", st.model_revision || "—"],
      ["Pronto", st.ready ? "sim" : "não — " + (st.not_ready_reason || "")], ["Versão", st.version],
      ["Perfil", st.profile.present ? st.profile.display_name + " (referência " + st.profile.reference_sha256_prefix + "…)" : "inexistente — " + (st.profile_error || "")],
    ]);
    const list = $("checklist"); list.replaceChildren();
    const labels = {
      motor_real_configurado: "Motor real configurado (não o simulado)", pesos_carregados: "Pesos carregados nesta máquina",
      perfil_com_consentimento_e_referencia: "Perfil com consentimento e gravação de referência íntegra",
      aprovacao_humana_das_amostras: "Aprovação humana depois de escutar as amostras",
    };
    for (const [key, label] of Object.entries(labels)) {
      const value = st.checklist[key]; const li = document.createElement("li");
      const ok = value === true; li.className = ok ? "ok" : "pending";
      li.textContent = (ok ? "✓ " : "• ") + label + (ok ? "" : (typeof value === "string" ? " — " + value : " — pendente"));
      list.append(li);
    }
    fill($("queue"), [["Em geração", st.queue.inflight], ["Admitidos (geração + espera)", st.queue.admitted + " de " + (st.queue.max_concurrency + st.queue.queue_max)],
      ["Áudios guardados (TTL " + st.limits.result_ttl_seconds + " s)", st.queue.stored_audios]]);
    $("text").maxLength = st.limits.max_text_chars;
    $("counter").textContent = "máx. " + st.limits.max_text_chars + " caracteres";
    const body = $("recent"); body.replaceChildren();
    for (const r of st.recent) {
      const tr = document.createElement("tr");
      for (const cell of [new Date(r.at * 1000).toLocaleTimeString("pt-BR"), r.request_id, r.status, r.seconds + " s", r.chars]) {
        const td = document.createElement("td"); td.textContent = String(cell); tr.append(td);
      }
      body.append(tr);
    }
    window.__lastStatus = st;
  }
  async function refresh() {
    try {
      const r = await api("/v1/panel/status");
      if (r.status === 401) { stop("Token recusado."); return; }
      if (!r.ok) { $("connectMsg").textContent = "Falha ao consultar o estado (" + r.status + ")."; return; }
      $("connectMsg").textContent = "Conectado."; render(await r.json());
    } catch (e) { $("connectMsg").textContent = "Sem resposta do serviço."; }
  }
  function stop(msg) { clearInterval(timer); token = ""; $("panel").hidden = true; $("connectMsg").textContent = msg; }

  $("connectBtn").addEventListener("click", () => {
    token = $("token").value.trim(); $("token").value = "";
    if (!token) { $("connectMsg").textContent = "Informe o token."; return; }
    clearInterval(timer); refresh(); timer = setInterval(refresh, 5000);
  });

  $("synthBtn").addEventListener("click", async () => {
    const text = $("text").value.trim();
    if (!text) { $("synthMsg").textContent = "Digite um texto."; return; }
    const id = "panel-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    $("synthBtn").disabled = true; $("synthMsg").textContent = "Gerando…"; $("player").hidden = true; $("synthLabel").hidden = true;
    try {
      const r = await api("/v1/synthesize", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_id: id, text, language: "pt" }) });
      const meta = await r.json();
      if (!r.ok) { $("synthMsg").textContent = "Recusado: " + (meta.error ? meta.error.code + " — " + meta.error.message : r.status); return; }
      const a = await api("/v1/audio/" + encodeURIComponent(meta.audio_id));
      if (!a.ok) { $("synthMsg").textContent = "Áudio indisponível (" + a.status + ")."; return; }
      const blob = await a.blob();
      const player = $("player"); if (player.src) URL.revokeObjectURL(player.src);
      player.src = URL.createObjectURL(blob); player.hidden = false;
      api("/v1/audio/" + encodeURIComponent(meta.audio_id), { method: "DELETE" }).catch(() => {});
      const simulated = meta.engine === "fake";
      const label = $("synthLabel"); label.hidden = false; label.className = "banner " + (simulated ? "sim" : "real");
      label.textContent = simulated
        ? "ÁUDIO SIMULADO (sinal de teste, " + meta.duration_seconds + " s). Não é a sua voz."
        : "Áudio gerado pelo motor " + meta.engine + " (revisão " + (meta.model_revision || "—") + ", " + meta.duration_seconds + " s) com o perfil " + meta.profile + ". Escute antes de aprovar.";
      $("synthMsg").textContent = "Pronto."; refresh();
    } catch (e) { $("synthMsg").textContent = "Falha de rede."; } finally { $("synthBtn").disabled = false; }
  });
})();
