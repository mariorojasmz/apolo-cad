import { useMemo, useState } from "react";
import { FunctionSquare, Library, Lock, PenTool, type LucideIcon } from "lucide-react";
import { useStore } from "../state/store";
import { iconFor } from "../ui/icons";
import { pestanasDe } from "./pestanas";
import { soloLecturaDe, textoSoloLectura } from "../state/soloLectura";

/* Ribbon con pestañas (sustituye la antigua Toolbar). Schema-driven de punta a punta: las
   pestañas y sus herramientas salen de la vista persona de /api/schemas (`pestana` y
   `category` de cada comando, vía `pestanasDe`), así que una categoría o un comando nuevo
   del backend aparece solo, con ícono FALLBACK si no se mapea en ui/icons.
   `title=` repite el nombre visible y nada más (el rótulo se corta con elipsis): lo que
   hace el comando lo dice la pista de su diálogo, que también se lee en una tableta.
   En sólo lectura (plan núcleo-abierto-extensiones-privadas, D4) los botones que crean o editan
   quedan deshabilitados y el motivo va a la vista al final de la fila (en la StatusBar no cabe). */

interface CmdBtnProps { icon: LucideIcon; label: string; onClick: () => void; disabled: boolean }

function CmdBtn({ icon: Icon, label, onClick, disabled }: CmdBtnProps) {
  return (
    <button className="cmd-btn" title={label} onClick={onClick} disabled={disabled}>
      <Icon size={20} strokeWidth={1.6} />
      <span>{label}</span>
    </button>
  );
}

export default function Ribbon() {
  const schemas = useStore((s) => s.schemas);
  const openDialog = useStore((s) => s.openDialog);
  const openVariables = useStore((s) => s.openVariables);
  const openLibrary = useStore((s) => s.openLibrary);
  const openSketcher = useStore((s) => s.openSketcher);
  const varCount = useStore((s) => s.scene?.document.variables.length ?? 0);
  const marcaSoloLectura = useStore((s) => soloLecturaDe(s.scene));
  const soloLectura = marcaSoloLectura !== null;
  const [tab, setTab] = useState("crear");

  const pestanas = useMemo(() => pestanasDe(schemas), [schemas]);
  const activa = pestanas.find((p) => p.clave === tab) ?? pestanas[0];

  return (
    <nav className="ribbon">
      <div className="ribbon-tabs">
        {pestanas.map((p) => (
          <button
            key={p.clave}
            className={`ribbon-tab ${activa?.clave === p.clave ? "active" : ""}`}
            onClick={() => setTab(p.clave)}
          >
            {p.rotulo}
          </button>
        ))}
        <span className="spacer" />
        <button className="icon-btn" title="Variables" onClick={() => openVariables(true)}>
          <FunctionSquare size={15} strokeWidth={1.7} />
          Variables{varCount > 0 ? ` (${varCount})` : ""}
        </button>
      </div>

      <div className="ribbon-row">
        {activa?.clave === "crear" && <CmdBtn icon={PenTool} label="Croquis" onClick={() => openSketcher()} disabled={soloLectura} />}
        {activa?.clave === "biblioteca" && (
          <CmdBtn icon={Library} label="Catálogo" onClick={() => openLibrary(true)} disabled={soloLectura} />
        )}
        {activa?.comandos.map((s) => (
          <CmdBtn
            key={s.type}
            icon={iconFor(s.type)}
            label={s.title}
            onClick={() => openDialog(s)}
            disabled={soloLectura}
          />
        ))}
        {marcaSoloLectura && (
          <span className="ribbon-aviso" role="status">
            <Lock size={14} strokeWidth={1.9} /> {textoSoloLectura(marcaSoloLectura)}
          </span>
        )}
      </div>
    </nav>
  );
}
