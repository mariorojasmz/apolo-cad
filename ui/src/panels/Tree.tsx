import { useMemo, useState } from "react";
import {
  Search, Eye, EyeOff, Focus, Filter, Trash2, ChevronRight, ChevronDown, ChevronsDownUp,
  Frame, Cog, Cylinder, CircleDot, Bolt, Shield, Gauge, Wrench, Box, Layers, Table,
  type LucideIcon,
} from "lucide-react";
import { selectFeatures, useStore } from "../state/store";
import { iconFor } from "../ui/icons";
import type { FeatureOut } from "../types";

/* Árbol del modelo en DOS niveles: subsistema (estructura, rodillos, tornillería…)
   → comando (las piezas de un mismo comando se pliegan en un nodo) → piezas.
   El subsistema de cada grupo se deriva, en orden, de: el tipo de super-comando,
   la categoría de catálogo, una PALABRA CLAVE del nombre (clave para máquinas
   hechas a mano, sin pieza de catálogo) y, como último recurso, el primer token
   del nombre. Todo en el cliente, sin tocar el backend. */

// orden fijo de los subsistemas conocidos; los buckets dinámicos van después, "A medida"/"Otros" al final
const ORDER = [
  "Estructura", "Transmisión", "Rodillos y tambores", "Banda y mesa", "Rodamientos",
  "Tornillería", "Guardas", "Sensores y control", "Carpintería", "A medida", "Otros",
];

const CAT2SUB: Record<string, string> = {
  perfiles: "Estructura", tubos_circulares: "Estructura", perfiles_abiertos: "Estructura",
  tubos_estructurales: "Estructura", patas: "Estructura", pies_niveladores: "Estructura",
  topes: "Estructura", guias_lineales: "Estructura",
  motorreductores: "Transmisión", transmision: "Transmisión", tensores_trotadora: "Transmisión",
  variadores: "Transmisión",
  rodillos: "Rodillos y tambores", tambores: "Rodillos y tambores",
  rodamientos: "Rodamientos", chumaceras: "Rodamientos",
  tornilleria: "Tornillería", tornilleria_madera: "Tornillería", pernos: "Tornillería",
  tuercas: "Tornillería",
  guardas: "Guardas",
  sensores: "Sensores y control", tableros: "Sensores y control", mandos: "Sensores y control",
  bisagras: "Carpintería", tiradores: "Carpintería", correderas: "Carpintería",
  cerraduras: "Carpintería", imanes_topes: "Carpintería", rieles_corredera: "Carpintería",
  correderas_colgantes: "Carpintería",
};

// super-comandos cuyo conjunto entero tiene un subsistema claro (anula los demás criterios)
const CMD2SUB: Record<string, string> = {
  create_take_up: "Rodillos y tambores", create_drive_roller: "Rodillos y tambores",
  create_weldment: "Estructura", create_frame: "Estructura",
};

// palabra clave del NOMBRE → subsistema (1.ª coincidencia gana; el orden importa: lo específico antes)
const NAME2SUB: [RegExp, string][] = [
  [/rodamiento|chumacera|balero/, "Rodamientos"],
  [/perno|tornillo|tuerca|seeger|arandela|clavija|esp[aá]rrago|allen|tirafondo|\bm\d|v[aá]stago|shank/, "Tornillería"],
  [/motor|reductor|acople|pi[ñn][oó]n|cadena|correa|transmisi|variador|borne|cuna/, "Transmisión"],
  [/rodillo|tambor|polea|\beje\b/, "Rodillos y tambores"],
  [/banda|cama|mesa|faja|desliz|repisa/, "Banda y mesa"],
  [/guarda|cubierta|protec|tapa|carcasa/, "Guardas"],
  [/sensor|fotoc[eé]l|tablero|bot[oó]n|paro|estop|hongo/, "Sensores y control"],
  [/bisagra|tirador|pomo|cerradura|vidrio|cristal/, "Carpintería"],
  [/pata|larguero|travesa|viga|perfil|bastidor|marco|poste|columna|\bbase\b|placa|m[eé]nsula|soporte|escuadra|[aá]ngulo|canal|tubo|nivelad|\bpie/, "Estructura"],
];

const SUB_ICON: Record<string, LucideIcon> = {
  Estructura: Frame, Transmisión: Cog, "Rodillos y tambores": Cylinder, "Banda y mesa": Table,
  Rodamientos: CircleDot, Tornillería: Bolt, Guardas: Shield, "Sensores y control": Gauge,
  Carpintería: Wrench, "A medida": Box, Otros: Layers,
};

/** ROL de una pieza: prefijo del super-comando (antes de « · ») o el nombre sin el sufijo «(n)».
   Es la clave de agrupación: une piezas del mismo rol AUNQUE las cree comandos distintos
   (p. ej. un travesaño suelto + un patrón de travesaños iguales). */
function roleOf(f: FeatureOut): string {
  const n = f.name;
  return n.includes(" · ") ? n.split(" · ")[0] : n.replace(/ \(\d+\)$/, "");
}
function baseLabel(members: FeatureOut[]): string {
  return roleOf(members[0]);
}
/** Primer token capitalizado (bucket dinámico cuando ninguna palabra clave coincide). */
function leadingToken(label: string): string {
  const t = label.trim().split(/[\s·]+/)[0] ?? "";
  return t ? t[0].toUpperCase() + t.slice(1) : "";
}

/** Medidas del bbox como «L × A × H mm» (mayor a menor: largo × las dos cotas de sección).
   DERIVADAS de la geometría → siempre actuales, nunca obsoletas (a diferencia del nombre). */
const fmtNum = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));
function dimsLabel(f: FeatureOut): string | null {
  const { min, max } = f.bbox;
  if (!min || !max || min.length < 3) return null;
  const d = [max[0] - min[0], max[1] - min[1], max[2] - min[2]]
    .map((x) => Math.round(Math.max(0, x) * 10) / 10)
    .sort((a, b) => b - a);
  if (d[0] <= 0) return null;
  return `${fmtNum(d[0])} × ${fmtNum(d[1])} × ${fmtNum(d[2])} mm`;
}
/** Medidas comunes de un grupo (si TODAS las piezas comparten cota, p. ej. un patrón). */
function commonDims(members: FeatureOut[]): string | null {
  const first = dimsLabel(members[0]);
  return first && members.every((m) => dimsLabel(m) === first) ? first : null;
}

export default function Tree() {
  const features = useStore(selectFeatures);
  const catalog = useStore((s) => s.catalog);
  const selection = useStore((s) => s.selection);
  const select = useStore((s) => s.select);
  const toggleSelect = useStore((s) => s.toggleSelect);
  const toggleVisibility = useStore((s) => s.toggleVisibility);
  const bulkVisibility = useStore((s) => s.bulkVisibility);
  const isolate = useStore((s) => s.isolate);
  const runCommand = useStore((s) => s.runCommand);
  const openContextMenu = useStore((s) => s.openContextMenu);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");

  const catBySub = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of catalog) m.set(c.ref, CAT2SUB[c.category] ?? "Otros");
    return m;
  }, [catalog]);

  const subsystemOfGroup = (members: FeatureOut[]): string => {
    const ct = members[0].command_type ?? "";
    if (CMD2SUB[ct]) return CMD2SUB[ct];
    // señal de catálogo (voto dominante), si alguna pieza la tiene
    const catVotes = new Map<string, number>();
    for (const m of members)
      if (m.component) {
        const s = catBySub.get(m.component);
        if (s && s !== "Otros") catVotes.set(s, (catVotes.get(s) ?? 0) + 1);
      }
    if (catVotes.size) return [...catVotes].sort((a, b) => b[1] - a[1])[0][0];
    // palabra clave del nombre (clave para piezas a medida)
    const base = baseLabel(members).toLowerCase();
    for (const [re, sub] of NAME2SUB) if (re.test(base)) return sub;
    return leadingToken(baseLabel(members)) || "A medida";
  };

  // filtro de búsqueda (nombre · id · referencia de catálogo)
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return features;
    return features.filter(
      (f) =>
        f.name.toLowerCase().includes(q) ||
        f.id.toLowerCase().includes(q) ||
        (f.component ?? "").toLowerCase().includes(q),
    );
  }, [features, query]);

  // agrupar por ROL (no por comando: une piezas iguales de comandos distintos),
  // luego repartir cada grupo de rol en su subsistema
  const tree = useMemo(() => {
    const byRole = new Map<string, FeatureOut[]>();
    for (const f of filtered) {
      const role = roleOf(f);
      const list = byRole.get(role) ?? [];
      list.push(f);
      byRole.set(role, list);
    }
    const buckets = new Map<string, [string, FeatureOut[]][]>();
    for (const [role, members] of byRole) {
      const sub = subsystemOfGroup(members);
      const arr = buckets.get(sub) ?? [];
      arr.push([role, members]);
      buckets.set(sub, arr);
    }
    const count = (s: string) => buckets.get(s)!.reduce((n, [, m]) => n + m.length, 0);
    const known = ORDER.filter((s) => s !== "A medida" && s !== "Otros" && buckets.has(s));
    const dynamic = [...buckets.keys()]
      .filter((k) => !ORDER.includes(k))
      .sort((a, b) => count(b) - count(a));
    const tail = ["A medida", "Otros"].filter((s) => buckets.has(s));
    return [...known, ...dynamic, ...tail].map(
      (s) => [s, buckets.get(s)!] as [string, [string, FeatureOut[]][]],
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, catBySub]);

  const searching = query.trim().length > 0;
  const isOpen = (key: string) => searching || !collapsed.has(key);
  const toggleCollapse = (key: string) => {
    const next = new Set(collapsed);
    next.has(key) ? next.delete(key) : next.add(key);
    setCollapsed(next);
  };

  // colapsa TODOS los nodos (subsistemas + grupos de comando) de una vez
  const collapseAll = () => {
    const keys = new Set<string>();
    for (const [sub, groups] of tree) {
      keys.add(`sub:${sub}`);
      for (const [role, members] of groups) if (members.length > 1) keys.add(`cmd:${role}`);
    }
    setCollapsed(keys);
  };
  const allCollapsed = tree.length > 0 && tree.every(([sub]) => collapsed.has(`sub:${sub}`));

  const onRowContext = (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    if (!selection.includes(id)) select([id]);
    openContextMenu({ x: e.clientX, y: e.clientY, targetId: id });
  };
  const focusFeature = (id: string) => {
    select([id]);
    window.dispatchEvent(new CustomEvent("apolo:fit", { detail: { id } }));
  };
  const onItemClick = (e: React.MouseEvent, id: string) => {
    if (e.ctrlKey || e.metaKey) toggleSelect(id);
    else select(selection.length === 1 && selection[0] === id ? [] : [id]);
  };

  const row = (f: FeatureOut, level: number, label?: string) => {
    const TypeIcon = iconFor(f.command_type ?? "");
    return (
      <li
        key={f.id}
        className={`${selection.includes(f.id) ? "selected" : ""} lvl${level}`}
        title={`${f.name}\nClic: seleccionar · Ctrl+clic: añadir · doble-clic: enfocar · clic derecho: menú`}
        onClick={(e) => onItemClick(e, f.id)}
        onDoubleClick={() => focusFeature(f.id)}
        onContextMenu={(e) => onRowContext(e, f.id)}
      >
        <button
          className="eye"
          title={f.visible ? "Ocultar" : "Mostrar"}
          onClick={(e) => { e.stopPropagation(); void toggleVisibility(f.id); }}
        >
          {f.visible ? <Eye size={13} /> : <EyeOff size={13} />}
        </button>
        <span className="swatch" style={{ background: f.color }} />
        {level < 2 && <TypeIcon size={12} className="type-ic" aria-hidden />}
        <span className={`name ${f.visible ? "" : "muted"}`}>{label ?? f.name}</span>
        {dimsLabel(f) && <span className="dim" title="Medidas (largo × ancho × alto, calculadas de la geometría)">{dimsLabel(f)}</span>}
        <span className="row-actions">
          <button title="Enfocar" onClick={(e) => { e.stopPropagation(); focusFeature(f.id); }}>
            <Focus size={13} />
          </button>
          <button title="Aislar (ocultar el resto)" onClick={(e) => { e.stopPropagation(); void isolate([f.id]); }}>
            <Filter size={13} />
          </button>
          <button title="Eliminar" onClick={(e) => { e.stopPropagation(); void runCommand("delete_feature", { feature: f.id }); }}>
            <Trash2 size={13} />
          </button>
        </span>
        <span className="fid">{f.id}</span>
      </li>
    );
  };

  return (
    <aside className="tree">
      <div className="tree-top">
        <h3>Árbol del modelo</h3>
        <div className="tree-top-right">
          <button
            className="tree-collapse"
            title="Colapsar todo"
            disabled={allCollapsed}
            onClick={collapseAll}
          >
            <ChevronsDownUp size={14} />
          </button>
          <span className="tree-count">{features.length} sólidos</span>
        </div>
      </div>
      <div className="tree-search">
        <Search size={13} />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Buscar pieza, id o referencia…"
        />
        {query && (
          <button className="clear" title="Limpiar" onClick={() => setQuery("")}>×</button>
        )}
      </div>

      {features.length === 0 && (
        <p className="hint">Escena vacía. Crea geometría con la toolbar o pídesela al asistente IA.</p>
      )}
      {features.length > 0 && tree.length === 0 && (
        <p className="hint">Sin coincidencias para «{query}».</p>
      )}

      <ul className="tree-root">
        {tree.map(([sub, groups]) => {
          const subKey = `sub:${sub}`;
          const subIds = groups.flatMap(([, m]) => m.map((f) => f.id));
          const allVisible = subIds.every((id) => features.find((f) => f.id === id)?.visible);
          const SubIcon = SUB_ICON[sub] ?? Box;
          return (
            <li key={subKey} className="tree-group">
              <div className="group-head sub-head" onClick={() => toggleCollapse(subKey)}>
                {isOpen(subKey) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <SubIcon size={15} className="type-ic" aria-hidden />
                <strong className="name">{sub}</strong>
                <span className="count-badge">{subIds.length}</span>
                <button
                  className="head-eye"
                  title={allVisible ? "Ocultar todo" : "Mostrar todo"}
                  onClick={(e) => { e.stopPropagation(); void bulkVisibility(subIds, !allVisible); }}
                >
                  {allVisible ? <Eye size={13} /> : <EyeOff size={13} />}
                </button>
              </div>
              {isOpen(subKey) && (
                <ul>
                  {groups.map(([role, members]) => {
                    if (members.length === 1) return row(members[0], 1);
                    const base = role;
                    const cmdKey = `cmd:${role}`;
                    const allIds = members.map((m) => m.id);
                    const groupSelected = allIds.every((id) => selection.includes(id));
                    const GroupIcon = iconFor(members[0].command_type ?? "");
                    const groupDims = commonDims(members);
                    return (
                      <li key={role} className="tree-group">
                        <div
                          className={`group-head lvl1 ${groupSelected ? "selected" : ""}`}
                          title="Clic: seleccionar el grupo entero"
                          onClick={() => select(groupSelected ? [] : allIds)}
                        >
                          <button
                            className="eye"
                            title={isOpen(cmdKey) ? "Plegar" : "Desplegar"}
                            onClick={(e) => { e.stopPropagation(); toggleCollapse(cmdKey); }}
                          >
                            {isOpen(cmdKey) ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                          </button>
                          <GroupIcon size={13} className="type-ic" aria-hidden />
                          <strong className="name">{base}</strong>
                          <span className="count-badge">{members.length}</span>
                          {groupDims && <span className="dim" title="Medidas comunes (calculadas de la geometría)">{groupDims}</span>}
                        </div>
                        {isOpen(cmdKey) && (
                          <ul>
                            {members.map((m) => {
                              const sub2 = m.name.startsWith(base)
                                ? m.name.slice(base.length).replace(/^[\s·]+/, "")
                                : m.name;
                              return row(m, 2, sub2 || m.id);
                            })}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
