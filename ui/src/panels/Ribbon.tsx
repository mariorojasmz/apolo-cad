import { useState } from "react";
import { FunctionSquare, Library, PenTool, type LucideIcon } from "lucide-react";
import { useStore } from "../state/store";
import { iconFor } from "../ui/icons";

/* Ribbon con pestañas (sustituye la antigua Toolbar). Sigue siendo schema-driven:
   las herramientas salen de /api/schemas por `category`, así que un comando nuevo del
   backend aparece solo en su pestaña (con icono FALLBACK si no se mapea en ui/icons).
   Si el backend añade una categoría nueva, basta con sumar una pestaña aquí. */

const TABS = [
  { key: "crear", label: "Crear" },
  { key: "croquis", label: "Croquis" },
  { key: "modificar", label: "Modificar" },
  { key: "ensamblaje", label: "Ensamblar" },
  { key: "biblioteca", label: "Biblioteca" },
  { key: "robotica", label: "Robótica" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

const ALWAYS: TabKey[] = ["crear", "modificar", "biblioteca"]; // tienen estáticos o comandos fijos

function CmdBtn({
  icon: Icon,
  label,
  title,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  title?: string;
  onClick: () => void;
}) {
  return (
    <button className="cmd-btn" title={title} onClick={onClick}>
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
  const [tab, setTab] = useState<TabKey>("crear");

  const by = (c: string) => schemas.filter((s) => s.category === c);
  const visible = TABS.filter((t) => ALWAYS.includes(t.key) || by(t.key).length > 0);
  const active: TabKey = visible.some((t) => t.key === tab) ? tab : "crear";

  return (
    <nav className="ribbon">
      <div className="ribbon-tabs">
        {visible.map((t) => (
          <button
            key={t.key}
            className={`ribbon-tab ${active === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
        <span className="spacer" />
        <button
          className="icon-btn"
          title="Variables del proyecto: úsalas en cualquier campo numérico con =nombre"
          onClick={() => openVariables(true)}
        >
          <FunctionSquare size={15} strokeWidth={1.7} />
          Variables{varCount > 0 ? ` (${varCount})` : ""}
        </button>
      </div>

      <div className="ribbon-row">
        {active === "crear" && (
          <CmdBtn
            icon={PenTool}
            label="Croquis"
            title="Croquis 2D con restricciones: dibuja a ojo, restringe y el solver lo hace exacto"
            onClick={() => openSketcher()}
          />
        )}
        {active === "biblioteca" && (
          <CmdBtn
            icon={Library}
            label="Catálogo"
            title="Catálogo de componentes con filtros y especificaciones"
            onClick={() => openLibrary(true)}
          />
        )}
        {by(active).map((s) => (
          <CmdBtn
            key={s.type}
            icon={iconFor(s.type)}
            label={s.title}
            title={s.description}
            onClick={() => openDialog(s)}
          />
        ))}
      </div>
    </nav>
  );
}
