import { useEffect } from "react";
import { X } from "lucide-react";
import { useStore } from "../state/store";
import { PANELES, esPanel, type PanelId } from "../dock/paneles";
import { escTienePrioridad } from "../viewport/shortcuts";
import { useVisor } from "./estado";
import { CIERRA_CON_ESC, cajonQueCierraEsc, esCampoDeTexto, type Lado } from "./cajones";
import "./cajones.css";

/* Cajones del visor (plan modo-visor, D3): flotan SOBRE el 3D, no lo achican. El izquierdo
   aloja el Árbol; el derecho, UN panel a la vez (el mismo componente que monta Dockview en
   Completo, de `dock/paneles.ts`). Mientras el grupo del viewport está maximizado, Dockview
   sigue montando su copia oculta del panel: hay dos instancias y se acepta (bitácora F0 c).
   Un cajón se monta al abrirse y se desmonta al cerrarse. */

function Cajon({ lado, panel }: { lado: Lado; panel: PanelId }) {
  const cerrar = useVisor((s) => s.cerrarCajon);
  const { titulo, Componente } = PANELES[panel];
  return (
    <aside className={`cajon cajon-${lado}`} aria-label={titulo}>
      <header className="cajon-cabecera">
        <h2>{titulo}</h2>
        <button
          type="button"
          className="cajon-cerrar"
          title="Cerrar"
          aria-label={`Cerrar ${titulo}`}
          onClick={() => cerrar(lado)}
        >
          <X size={16} />
        </button>
      </header>
      <div className="cajon-cuerpo">
        <Componente />
      </div>
    </aside>
  );
}

/** Esc cierra el cajón abierto (el derecho primero) ANTES que los atajos del viewport, que con
   Esc limpian la selección (`viewport/shortcuts.ts`): escucha en fase de captura y corta la
   propagación sólo si cerró un cajón. Un diálogo, el menú contextual o el menú «Más» tienen
   prioridad; dentro de un campo de texto, Esc es del campo. */
function useEscCierraCajones(): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const v = useVisor.getState();
      const lado = cajonQueCierraEsc(v, {
        prioridad: escTienePrioridad(useStore.getState()) || !!document.querySelector(`[${CIERRA_CON_ESC}]`),
        enCampo: esCampoDeTexto(e.target as HTMLElement | null),
      });
      if (!lado) return;
      v.cerrarCajon(lado);
      e.stopPropagation();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);
}

export default function Cajones() {
  const izq = useVisor((s) => s.cajonIzq);
  const der = useVisor((s) => s.cajonDer);
  useEscCierraCajones();
  return (
    <>
      {izq && <Cajon lado="izq" panel="tree" />}
      {der && esPanel(der) && <Cajon lado="der" panel={der} />}
    </>
  );
}
