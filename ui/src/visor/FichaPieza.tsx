import { useEffect, useState } from "react";
import { api } from "../api";
import { useStore } from "../state/store";
import type { MasaPieza } from "../types";
import { useVisor } from "./estado";
import BotonCopiar from "./BotonCopiar";
import { CacheMasa, SIN_DATO, formatearMedidas, formatearPeso, nombreMaterial } from "./ficha";
import "./cajones.css";

/* Ficha de pieza del visor (plan modo-visor, D7): con UNA pieza seleccionada y sin cajón derecho
   abierto, una tarjeta chica arriba a la derecha, debajo del ViewCube. Nombre e id (el id es lo
   que el agente necesita), medidas del bbox de la escena, y material y peso de
   `GET /api/mass-properties`. «Ver todo» abre Propiedades en el cajón derecho. */

const masas = new CacheMasa<MasaPieza>();
/** Espera antes de pedir la masa: una ráfaga de cambios (flechas, lotes del agente) hace un fetch. */
const ESPERA_MS = 150;

export default function FichaPieza() {
  const id = useStore((s) => (s.selection.length === 1 ? s.selection[0] : null));
  const scene = useStore((s) => s.scene);
  const derAbierto = useVisor((s) => s.cajonDer !== null);
  const abrirDer = useVisor((s) => s.abrirDer);
  const f = id ? scene?.features.find((x) => x.id === id) : undefined;
  const rev = f?.rev ?? 0;
  // la última masa leída y de qué pieza es: mientras se vuelve a leer la MISMA, sigue a la vista
  const [masa, setMasa] = useState<{ id: string; dato: MasaPieza | null } | null>(null);
  const enCache = id && scene ? masas.leer(scene, id, rev) : undefined;

  useEffect(() => {
    if (!id || !scene || derAbierto || masas.leer(scene, id, rev)) return;
    let vigente = true;
    const reloj = setTimeout(() => {
      api.massProperties([id]).then(
        (r) => {
          const dato = r.piezas.find((p) => p.id === id) ?? null;
          if (!vigente) return;
          if (dato) masas.guardar(scene, id, rev, dato);
          setMasa({ id, dato });
        },
        () => {
          if (vigente) setMasa({ id, dato: null }); // p. ej. la pieza ya no existe: «—»
        },
      );
    }, ESPERA_MS);
    return () => {
      vigente = false;
      clearTimeout(reloj);
    };
  }, [id, rev, scene, derAbierto]);

  if (!id || !f || derAbierto) return null;
  const dato = enCache ?? (masa?.id === id ? masa.dato : null);

  return (
    <section className="ficha-pieza" aria-label="Pieza seleccionada">
      <header className="fp-cabecera">
        <span className="fp-color" style={{ background: f.color }} />
        <div className="fp-titulo">
          <b title={f.name}>{f.name}</b>
          <span className="fp-id">{f.id}</span>
        </div>
      </header>
      <dl className="fp-datos">
        <dt>Material</dt>
        <dd>{dato ? nombreMaterial(dato.material) : SIN_DATO}</dd>
        <dt>Medidas</dt>
        <dd>{formatearMedidas(f.bbox)}</dd>
        <dt>Peso</dt>
        <dd>{dato ? formatearPeso(dato.masa_kg) : SIN_DATO}</dd>
      </dl>
      <div className="fp-acciones">
        <BotonCopiar nombre={f.name} id={f.id} className="primary" claseAMano="fp-a-mano" tamIcono={14} />
        <button type="button" className="ghost" onClick={() => abrirDer("properties")}>
          Ver todo
        </button>
      </div>
    </section>
  );
}
