import { useStore } from "../state/store";

/* El historial ES el documento: el log de comandos reproducible. */

export default function HistoryPanel() {
  const doc = useStore((s) => s.scene?.document);
  const show = useStore((s) => s.showHistory);
  if (!show || !doc) return null;

  return (
    <section className="history">
      <h3>Historial de comandos</h3>
      <ol>
        {doc.commands.map((c) => (
          <li key={c.id}>
            <code>{c.id}</code> <strong>{c.type}</strong>
            <span className="params">{JSON.stringify(c.params)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
