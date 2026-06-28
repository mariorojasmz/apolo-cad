import { selectFeatures, useStore } from "../state/store";
import SchemaForm from "../forms/SchemaForm";

export default function CommandDialog() {
  const schema = useStore((s) => s.dialogSchema);
  const features = useStore(selectFeatures);
  const openDialog = useStore((s) => s.openDialog);
  const runCommand = useStore((s) => s.runCommand);
  const busy = useStore((s) => s.busy);

  if (!schema) return null;

  return (
    <div className="modal-backdrop" onClick={() => !busy && openDialog(null)}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{schema.title}</h3>
        <p className="hint">{schema.description}</p>
        <SchemaForm
          schema={schema.schema}
          features={features}
          submitLabel="Ejecutar"
          busy={busy}
          onCancel={() => openDialog(null)}
          onSubmit={(values) => void runCommand(schema.type, values)}
        />
      </div>
    </div>
  );
}
