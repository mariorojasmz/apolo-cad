import { useEffect, useState } from "react";
import { api } from "../api";
import { useStore } from "../state/store";

/* Panel Cinemática: deslizadores por junta que mueven el modelo en el
   viewport (cinemática directa, solo visual), estudios de movimiento CON NOMBRE
   (varias animaciones reproducibles por separado) y export URDF/SDF. */

const TYPE_LABEL: Record<string, string> = {
  fija: "fija",
  giratoria: "giratoria (°)",
  continua: "continua (°)",
  prismatica: "prismática (mm)",
};

/** Valores de junta interpolados linealmente en el instante t (espejo del backend). */
function valuesAt(kfs: { t: number; values: Record<string, number> }[], t: number): Record<string, number> {
  if (!kfs.length) return {};
  const s = [...kfs].sort((a, b) => a.t - b.t);
  if (t <= s[0].t) return { ...s[0].values };
  if (t >= s[s.length - 1].t) return { ...s[s.length - 1].values };
  for (let i = 0; i < s.length - 1; i++) {
    const lo = s[i];
    const hi = s[i + 1];
    if (t >= lo.t && t <= hi.t) {
      const span = hi.t - lo.t;
      const f = span <= 1e-9 ? 0 : (t - lo.t) / span;
      const out: Record<string, number> = {};
      for (const n of new Set([...Object.keys(lo.values), ...Object.keys(hi.values)])) {
        const a = lo.values[n] ?? hi.values[n] ?? 0;
        const b = hi.values[n] ?? lo.values[n] ?? 0;
        out[n] = a + (b - a) * f;
      }
      return out;
    }
  }
  return { ...s[s.length - 1].values };
}

export default function KinematicsPanel() {
  const kinematics = useStore((s) => s.kinematics);
  const constraints = useStore((s) => s.constraints);
  const jointValues = useStore((s) => s.jointValues);
  const setJointValue = useStore((s) => s.setJointValue);
  const driveJoint = useStore((s) => s.driveJoint);
  const resetJointValues = useStore((s) => s.resetJointValues);
  const refreshKinematics = useStore((s) => s.refreshKinematics);
  const deleteJoint = useStore((s) => s.deleteJoint);
  const motionStudies = useStore((s) => s.motionStudies);
  const activeStudy = useStore((s) => s.activeStudy);
  const setActiveStudy = useStore((s) => s.setActiveStudy);
  const refreshMotion = useStore((s) => s.refreshMotion);
  const saveMotion = useStore((s) => s.saveMotion);
  const deleteStudy = useStore((s) => s.deleteStudy);
  const setJointValues = useStore((s) => s.setJointValues);
  const features = useStore((s) => s.scene?.features ?? null);
  const commands = useStore((s) => s.scene?.document.commands ?? null);
  const runTracked = useStore((s) => s.runTracked);
  const busy = useStore((s) => s.busy);
  const [poseCheck, setPoseCheck] = useState<string | null>(null);
  const [poseBusy, setPoseBusy] = useState(false);
  const [captureT, setCaptureT] = useState("0");
  const [playingStudy, setPlayingStudy] = useState<string | null>(null);
  const [scanMsg, setScanMsg] = useState<string | null>(null);
  const [scanBusy, setScanBusy] = useState(false);

  useEffect(() => {
    void refreshKinematics();
    void refreshMotion();
  }, [refreshKinematics, refreshMotion]);

  // estudio que se está reproduciendo (puede diferir del activo en edición)
  const playSt = motionStudies.find((s) => s.name === playingStudy) ?? null;
  const playDur = playSt?.duration ?? 0;
  const playKfs = playSt?.keyframes ?? [];

  useEffect(() => {
    if (!playSt || playDur <= 0) return;
    let raf = 0;
    const start = performance.now();
    const tick = () => {
      const t = ((performance.now() - start) / 1000) % playDur;
      setJointValues(valuesAt(playKfs, t));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playSt, playDur, playKfs, setJointValues]);

  // si el estudio que se reproducía deja de existir, detener
  useEffect(() => {
    if (playingStudy && !motionStudies.some((s) => s.name === playingStudy)) setPlayingStudy(null);
  }, [playingStudy, motionStudies]);

  const joints = kinematics?.joints ?? [];
  const posing = Object.values(jointValues).some((v) => v !== 0);
  const dependents = new Set(constraints.map((c) => c.joint));
  const featName = (id: string) => features?.find((f) => f.id === id)?.name ?? id;

  const studyNames = motionStudies.map((s) => s.name);
  const isDraft = activeStudy != null && !studyNames.includes(activeStudy);
  const active = motionStudies.find((s) => s.name === activeStudy) ?? null;
  const activeKfs = active?.keyframes ?? [];
  const activeDur = active?.duration ?? 0;

  const newStudy = () => {
    const name = window.prompt("Nombre del estudio de movimiento", `Estudio ${motionStudies.length + 1}`);
    const trimmed = name?.trim();
    if (!trimmed) return;
    setActiveStudy(trimmed); // borrador: se persiste al capturar el 1.er fotograma
    setScanMsg(null);
  };

  const capture = () => {
    if (!activeStudy) return;
    void saveMotion(activeStudy, [
      ...activeKfs.filter((k) => k.t !== Number(captureT)),
      { t: Number(captureT), values: { ...jointValues } },
    ]);
  };

  return (
    <section className="history kin">
      <div className="bom-head">
        <h3>Cinemática · {joints.length} juntas</h3>
        <div className="kin-actions">
          {posing && (
            <>
              <button onClick={resetJointValues} title="Vuelve a la pose de diseño">
                ⌂ Pose cero
              </button>
              <button
                title="Interferencias del mecanismo en la pose actual"
                disabled={poseBusy}
                onClick={() => {
                  setPoseCheck("…");
                  setPoseBusy(true);
                  void runTracked("checks", () => api.checks({ joint_values: jointValues })).then((r) => {
                    setPoseBusy(false);
                    if (!r) {
                      setPoseCheck("error al comprobar");
                      return;
                    }
                    const n = r.interferencias.interferencias.length;
                    const avisos = r.interferencias.avisos_pose?.length
                      ? ` · ${r.interferencias.avisos_pose.join("; ")}`
                      : "";
                    setPoseCheck(
                      n === 0
                        ? `✓ sin colisiones en esta pose${avisos}`
                        : `✕ ${n} colisión(es): ${r.interferencias.interferencias
                            .map((c) => `${c.nombre_a} ↔ ${c.nombre_b}`)
                            .slice(0, 3)
                            .join(", ")}${avisos}`,
                    );
                  });
                }}
              >
                {poseBusy ? "Comprobando…" : "💥 Colisión en pose"}
              </button>
            </>
          )}
          <button onClick={() => window.open("/api/export/urdf", "_blank")} title="ROS / Isaac Sim">
            Exportar URDF
          </button>
          <button onClick={() => window.open("/api/export/sdf", "_blank")} title="Gazebo">
            Exportar SDF
          </button>
        </div>
      </div>

      {kinematics?.errors.map((e, i) => (
        <p key={i} className="estado-error">✕ {e}</p>
      ))}
      {poseCheck && (
        <p className={poseCheck.startsWith("✓") ? "estado-ok" : "estado-error"}>{poseCheck}</p>
      )}

      {joints.length === 0 ? (
        <p className="hint">
          Sin juntas. Crea un <strong>Brazo robótico</strong> desde la toolbar (grupo Robótica), o une dos
          sólidos con <strong>Junta</strong>.
        </p>
      ) : (
        <div className="kin-joints">
          <div className="kin-grid">
            {joints.map((j) => {
              const value = jointValues[j.name] ?? 0;
              const dependent = dependents.has(j.name);
              const disabled = j.type === "fija" || dependent;
              return (
                <div className="kin-row" key={j.name}>
                  <div className="kin-info">
                    <strong>{j.name}</strong>
                    <span className="hint">
                      {dependent ? "auto · riel" : TYPE_LABEL[j.type]} · {featName(j.parent)} → {featName(j.child)}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={j.lower}
                    max={j.upper}
                    step={1}
                    value={value}
                    disabled={disabled}
                    title={dependent ? "Resuelta por la restricción de riel (no se arrastra)" : undefined}
                    onChange={(e) =>
                      (constraints.length ? driveJoint : setJointValue)(j.name, Number(e.target.value))
                    }
                  />
                  <span className="kin-value" title={String(value)}>
                    {Math.round(value * 10) / 10}{j.type === "prismatica" ? " mm" : "°"}
                  </span>
                  {commands?.find((c) => c.id === j.command_id)?.type === "add_joint" ? (
                    <button className="ghost" title="Eliminar junta" disabled={busy} onClick={() => void deleteJoint(j.name)}>
                      ✕
                    </button>
                  ) : (
                    <span className="fid" title="Junta de plantilla: edítala desde su comando">🔒</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
      {constraints.length > 0 && (
        <p className="hint">
          🔗 {constraints.length} restricción(es) de riel activas: arrastra los <strong>drivers</strong>; las
          juntas «auto · riel» se resuelven solas para mantener el carro sobre el riel.
        </p>
      )}

      {joints.length > 0 && (
        <div className="kin-anim">
          <div className="bom-head">
            <h4>Estudios de movimiento · {motionStudies.length}</h4>
            <div className="kin-actions">
              <button onClick={newStudy} title="Crea un estudio de movimiento nuevo">
                ➕ Nuevo estudio
              </button>
            </div>
          </div>

          {/* fila de estudios: cada uno con su ▶ Reproducir y ✕ */}
          <div className="study-chips">
            {motionStudies.map((s) => {
              const isActive = s.name === activeStudy;
              const isPlaying = s.name === playingStudy;
              return (
                <div className={`study-chip${isActive ? " active" : ""}`} key={s.name}>
                  <button
                    className="study-name"
                    title="Seleccionar para editar"
                    onClick={() => setActiveStudy(s.name)}
                  >
                    {s.name}
                    <span className="study-meta">{s.keyframes.length} fot · {s.duration}s</span>
                  </button>
                  <button
                    className={`study-play${isPlaying ? " active" : ""}`}
                    disabled={s.keyframes.length < 2}
                    title={s.keyframes.length < 2 ? "Necesita ≥2 fotogramas" : "Reproducir este estudio"}
                    onClick={() => {
                      setActiveStudy(s.name);
                      setPlayingStudy(isPlaying ? null : s.name);
                    }}
                  >
                    {isPlaying ? "⏸" : "▶"}
                  </button>
                  <button
                    className="ghost"
                    title="Eliminar estudio"
                    disabled={busy}
                    onClick={() => {
                      if (window.confirm(`¿Eliminar el estudio «${s.name}»?`)) void deleteStudy(s.name);
                    }}
                  >
                    ✕
                  </button>
                </div>
              );
            })}
            {isDraft && (
              <div className="study-chip active" key="__draft">
                <span className="study-name">
                  {activeStudy}
                  <span className="study-meta">nuevo · sin guardar</span>
                </span>
              </div>
            )}
          </div>

          {motionStudies.length === 0 && !isDraft ? (
            <p className="hint">
              Aún no hay estudios. Pulsa <strong>➕ Nuevo estudio</strong>, pose el modelo con los sliders y
              <strong> captura fotogramas</strong> en distintos tiempos; luego <strong>▶</strong> para verlo.
            </p>
          ) : !activeStudy ? (
            <p className="hint">Selecciona un estudio para editarlo.</p>
          ) : (
            <>
              <div className="bom-head">
                <h4>
                  Editar «{activeStudy}» · {activeKfs.length} fotogramas{activeDur > 0 ? ` · ${activeDur}s` : ""}
                </h4>
                <div className="kin-actions">
                  <input
                    value={captureT}
                    onChange={(e) => setCaptureT(e.target.value)}
                    title="tiempo del fotograma (s)"
                    style={{ width: 56 }}
                  />
                  <button
                    title="Guarda la pose actual de los sliders como fotograma en este tiempo"
                    onClick={capture}
                  >
                    ⊕ Capturar fotograma
                  </button>
                  <button
                    disabled={activeKfs.length < 2 || scanBusy}
                    title="Comprueba colisiones a lo largo de todo el recorrido"
                    onClick={() => {
                      setScanMsg("…");
                      setScanBusy(true);
                      void runTracked("scanMotion", () => api.scanMotion(activeStudy, 24)).then((r) => {
                        setScanBusy(false);
                        if (!r) {
                          setScanMsg("error al comprobar");
                          return;
                        }
                        const n = r.colisiones.length;
                        setScanMsg(
                          n === 0
                            ? "✓ sin colisiones en el recorrido"
                            : `✕ colisión en ${n} instante(s): t=${r.colisiones.map((c) => c.t).slice(0, 5).join(", ")} s`,
                        );
                      });
                    }}
                  >
                    {scanBusy ? "Comprobando…" : "💥 Comprobar recorrido"}
                  </button>
                </div>
              </div>
              {scanMsg && (
                <p className={scanMsg.startsWith("✓") ? "estado-ok" : "estado-error"}>{scanMsg}</p>
              )}
              {activeKfs.length === 0 ? (
                <p className="hint">
                  Pose el modelo con los sliders y pulsa <strong>Capturar fotograma</strong> en distintos
                  tiempos; necesitas ≥2 para reproducir.
                </p>
              ) : (
                <div className="kin-grid">
                  {activeKfs.map((k, i) => (
                    <div className="kin-row" key={i}>
                      <div className="kin-info">
                        <strong>t = {k.t} s</strong>
                        <span className="hint">{Object.keys(k.values).length} juntas</span>
                      </div>
                      <button
                        className="ghost"
                        title="Eliminar fotograma"
                        onClick={() => void saveMotion(activeStudy, activeKfs.filter((_, j) => j !== i))}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {posing && (
        <p className="hint">
          Pose de previsualización: no modifica el documento. El gizmo se desactiva hasta volver a la pose cero.
        </p>
      )}
    </section>
  );
}
