import { useEffect, useRef, useState } from "react";
import { ChevronUp } from "lucide-react";
import { useStore } from "../state/store";
import { HERRAMIENTAS, PANELES, type PanelId } from "../dock/paneles";
import { PANEL_ICONS } from "../ui/icons";
import { useVisor } from "./estado";
import { CIERRA_CON_ESC, panelesDelMenu } from "./cajones";
import "./cajones.css";

/* Barra de paneles del visor (plan modo-visor, D4), flotante abajo al centro: Árbol · BOM ·
   Validar · Historial · Más · Asistente IA. Abre los cajones (`Cajon.tsx`); el botón del panel
   abierto queda resaltado. Validar va sin conteo: no hay uno barato sin correr la validación
   (bitácora F0 e). Los rótulos e íconos son los de la StatusBar. */

/** Herramientas con botón propio, en el orden de la barra; el resto va en «Más». */
const CON_BOTON: PanelId[] = ["bom", "checks", "history"];
const DEL_MENU = panelesDelMenu(HERRAMIENTAS, CON_BOTON);

function BotonPanel({ id, on, onClick }: { id: PanelId; on: boolean; onClick: () => void }) {
  const Icono = PANEL_ICONS[id];
  const rotulo = PANELES[id].rotulo;
  return (
    <button type="button" className={on ? "on" : ""} aria-pressed={on} title={rotulo} onClick={onClick}>
      <Icono size={16} strokeWidth={1.8} />
      <span className="bp-rotulo">{rotulo}</span>
    </button>
  );
}

export default function BarraPaneles() {
  const izq = useVisor((s) => s.cajonIzq);
  const der = useVisor((s) => s.cajonDer);
  const toggleIzq = useVisor((s) => s.toggleIzq);
  const abrirDer = useVisor((s) => s.abrirDer);
  const [menu, setMenu] = useState(false);
  const caja = useRef<HTMLSpanElement>(null);

  // el menú «Más» se cierra con un clic afuera o con Esc (antes que los cajones: CIERRA_CON_ESC)
  useEffect(() => {
    if (!menu) return;
    const fuera = (e: PointerEvent) => {
      if (!caja.current?.contains(e.target as Node)) setMenu(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setMenu(false);
      e.stopPropagation();
    };
    document.addEventListener("pointerdown", fuera, true);
    window.addEventListener("keydown", esc, true);
    return () => {
      document.removeEventListener("pointerdown", fuera, true);
      window.removeEventListener("keydown", esc, true);
    };
  }, [menu]);

  const elegir = (accion: () => void) => {
    setMenu(false);
    accion();
  };
  const masOn = der !== null && (DEL_MENU as string[]).includes(der);

  return (
    <nav className="barra-paneles" aria-label="Paneles">
      <BotonPanel id="tree" on={izq} onClick={toggleIzq} />
      <span className="bp-sep" />
      {CON_BOTON.map((id) => (
        <BotonPanel key={id} id={id} on={der === id} onClick={() => abrirDer(id)} />
      ))}
      <span className="bp-mas" ref={caja}>
        <button
          type="button"
          className={masOn || menu ? "on" : ""}
          aria-haspopup="menu"
          aria-expanded={menu}
          title="Más"
          onClick={() => setMenu(!menu)}
        >
          <ChevronUp size={16} strokeWidth={1.8} />
          <span className="bp-rotulo">Más</span>
        </button>
        {menu && (
          <span className="bp-menu" role="menu" aria-label="Más paneles" {...{ [CIERRA_CON_ESC]: "" }}>
            <button
              type="button"
              role="menuitem"
              onClick={() => elegir(() => useStore.getState().openVariables(true))}
            >
              Variables
            </button>
            {DEL_MENU.map((id) => (
              <button
                key={id}
                type="button"
                role="menuitem"
                className={der === id ? "on" : ""}
                onClick={() => elegir(() => abrirDer(id))}
              >
                {PANELES[id].rotulo}
              </button>
            ))}
          </span>
        )}
      </span>
      <span className="bp-sep" />
      <BotonPanel id="chat" on={der === "chat"} onClick={() => abrirDer("chat")} />
    </nav>
  );
}
