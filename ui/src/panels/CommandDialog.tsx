import { selectFeatures, useStore } from "../state/store";
import SchemaForm from "../forms/SchemaForm";
import Pista from "../ui/Pista";
import VerDetalle from "../ui/VerDetalle";
import { textoTecnico } from "../ui/textoTecnico";

/* Diálogo de un comando: título, la pista (qué hace, en una frase), el detalle técnico
   plegado y el formulario. La descripción completa del agente NO se pinta aquí: llega
   limpia en `detalle` desde la vista persona del servidor y va a pedido. */

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
        <Pista>{schema.pista}</Pista>
        {schema.detalle && <VerDetalle resumen="Detalle técnico">{textoTecnico(schema.detalle)}</VerDetalle>}
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
