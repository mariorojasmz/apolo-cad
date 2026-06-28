import { useEffect, useRef, useState } from "react";
import { useStore } from "../state/store";
import type { ChatAction } from "../types";

export default function ChatPanel() {
  const chat = useStore((s) => s.chat);
  const chatBusy = useStore((s) => s.chatBusy);
  const busy = useStore((s) => s.busy);
  const sendChat = useStore((s) => s.sendChat);
  const resolveActions = useStore((s) => s.resolveActions);
  const autoMode = useStore((s) => s.autoMode);
  const setAutoMode = useStore((s) => s.setAutoMode);
  const [text, setText] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [chat]);

  const submit = () => {
    const t = text.trim();
    if (!t || chatBusy) return;
    setText("");
    void sendChat(t);
  };

  return (
    <section className="chat">
      <div className="chat-head">
        <h3>✦ Asistente IA</h3>
        <label
          className={`auto-toggle ${autoMode ? "on" : ""}`}
          title="El agente ejecuta, valida y corrige sin pedir aprobación lote a lote. Todo queda en el historial y es deshacible."
        >
          <input type="checkbox" checked={autoMode} onChange={(e) => setAutoMode(e.target.checked)} />
          ⚡ Modo auto
        </label>
      </div>
      <div className="chat-scroll" ref={scrollRef}>
        {chat.length === 0 && (
          <p className="hint">
            Describe lo que quieres construir. Ej.: «crea un marco de perfil 40x40 de 2000×1000 mm».
          </p>
        )}
        {chat.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.tools && m.tools.length > 0 && (
              <div className="tool-chips">
                {m.tools.map((t, j) => (
                  <span key={j} className="tool-chip">⚙ {t}</span>
                ))}
              </div>
            )}
            {m.content && <p>{m.content}</p>}
            {m.error && <p className="error">{m.error}</p>}
            {m.actions && (
              <div className="action-card">
                <header>
                  Propuesta · {m.actions.length} {m.actions.length === 1 ? "acción" : "acciones"}
                </header>
                <ol>
                  {m.actions.map((a, j) => (
                    <ActionRow key={j} action={a} />
                  ))}
                </ol>
                {m.actionsStatus === "pending" && (
                  <div className="card-buttons">
                    <button className="primary" disabled={busy} onClick={() => void resolveActions(i, true)}>
                      {busy ? "Aplicando…" : "Aceptar todo"}
                    </button>
                    <button className="ghost" disabled={busy} onClick={() => void resolveActions(i, false)}>
                      Rechazar
                    </button>
                  </div>
                )}
                {m.actionsStatus === "accepted" && (
                  <p className="status ok">✓ Ejecutado en el modelo{autoMode ? " (modo auto)" : ""}</p>
                )}
                {m.actionsStatus === "rejected" && <p className="status">Rechazado</p>}
                {m.actionsStatus === "error" && <p className="status error">Falló la ejecución (ver aviso)</p>}
              </div>
            )}
          </div>
        ))}
        {chatBusy && <p className="hint">pensando…</p>}
      </div>
      <div className="chat-input">
        <textarea
          rows={2}
          placeholder="Describe un cambio…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className="primary" disabled={chatBusy || !text.trim()} onClick={submit}>
          Enviar
        </button>
      </div>
    </section>
  );
}

function ActionRow({ action }: { action: ChatAction }) {
  const [open, setOpen] = useState(false);
  const code = typeof action.params.code === "string" ? action.params.code : null;
  const summary = Object.entries(action.params)
    .filter(([k]) => k !== "code")
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
  return (
    <li>
      <button className="action-row" onClick={() => setOpen(!open)} title={action.reason}>
        <strong>{action.type}</strong>
        <span className="params">{code ? "código ▾ · " : ""}{summary}</span>
      </button>
      {open && (
        <>
          <p className="reason">{action.reason}</p>
          {code && <pre className="action-code">{code}</pre>}
        </>
      )}
    </li>
  );
}
