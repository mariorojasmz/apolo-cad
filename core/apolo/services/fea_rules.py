"""Reglas FEA con VIGENCIA (V5.6/V7.4) de un documento: los resultados guardados en
`doc.fea` convertidos en reglas para `/api/checks` y la memoria de cálculo. El llamador
sostiene STATE_LOCK. Reglas: `services/CLAUDE.md` § FEA."""

from __future__ import annotations


def fea_rules(doc) -> list[dict]:
    """Convierte los resultados FEA guardados (doc.fea) en reglas para checks y
    memoria, con chequeo de VIGENCIA: si la pieza/ensamblaje ya no existe o su volumen
    cambió >0.1 % desde el análisis, la regla degrada a aviso (re-ejecutar). Cubre el
    FEA de PIEZA (clave=feature_id) y el de ENSAMBLAJE bonded (clave=`group:<nombre>`,
    vigencia por volumen CONJUNTO de sus piezas). Llamar bajo STATE_LOCK."""
    rules: list[dict] = []
    for key, res in doc.fea.items():
        es_grupo = res.get("tipo") == "ensamblaje_bonded" or str(key).startswith("group:")
        if es_grupo:
            regla = f"FEA bastidor · {res.get('grupo', str(key).split(':', 1)[-1])}"
            fids = res.get("piezas_fids") or []
            faltan = [f for f in fids if f not in doc.scene]
            if faltan or not fids:
                rules.append({"regla": regla, "estado": "aviso",
                              "detalle": "Piezas del ensamblaje analizado ya no existen: "
                                         f"{', '.join(faltan) if faltan else 'sin registro'}.",
                              "recomendacion": "Re-ejecuta fea_assembly sobre el grupo."})
                continue
            vol_now = float(sum(float(getattr(doc.scene[f].shape, "volume", 0) or 0) for f in fids))
            cmd = "fea_assembly"
        else:
            regla = f"FEA · {res.get('pieza', key)}"
            feat = doc.scene.get(key)
            if feat is None:
                rules.append({"regla": regla, "estado": "aviso",
                              "detalle": "La pieza del análisis FEA ya no existe en la escena.",
                              "recomendacion": "Borra el resultado o re-ejecuta fea_static."})
                continue
            vol_now = float(getattr(feat.shape, "volume", 0) or 0)
            cmd = "fea_static"
        vol_ref = float(res.get("volumen_mm3") or 0)
        if vol_ref and abs(vol_now - vol_ref) > 1e-3 * vol_ref:
            rules.append({"regla": regla, "estado": "aviso",
                          "detalle": f"La geometría cambió desde el análisis "
                                     f"({vol_ref:.0f} → {vol_now:.0f} mm³): resultado obsoleto.",
                          "recomendacion": f"Re-ejecuta {cmd} para refrescar el FS."})
            continue
        rule = {"regla": regla, "estado": res.get("estado", "aviso"),
                "detalle": res.get("detalle", ""), "calc": res.get("calc")}
        if es_grupo and res.get("piezas"):
            # tabla por pieza en la memoria: las de MENOR FS primero (las que gobiernan).
            # Con historial de CONVERGENCIA el cupo de piezas baja a 5 (el tope del
            # calc_report es 12 filas y la serie de malla vale más que la cola de FS altos)
            conv = res.get("convergencia") or []
            cap = 5 if conv else 8
            filas = ["Pieza · σ_vm [MPa] · FS · estado"]
            for p in res["piezas"][:cap]:
                fs_txt = f"{p['fs']:g}" if p.get("fs") is not None else "—"
                filas.append(f"{str(p['pieza'])[:26]} · {p['sigma_vm_max_mpa']:g} · "
                             f"{fs_txt} · {p.get('estado', '')}")
            if len(res["piezas"]) > cap:
                filas.append(f"… y {len(res['piezas']) - cap} pieza(s) más")
            if conv:
                filas.append("CONVERGENCIA DE MALLA (runs previos → vigente)")
                for h in conv:
                    filas.append(f"size {h.get('mesh_size_mm'):g} mm · FS {h.get('fs'):g} "
                                 f"({str(h.get('pieza_critica', ''))[:18]}) · "
                                 f"δ {h.get('desplazamiento_max_mm'):g} mm")
                filas.append(f"size {res.get('mesh_size_mm'):g} mm · FS {res.get('fs'):g} "
                             f"({str(res.get('pieza_critica', ''))[:18]}) · "
                             f"δ {res.get('desplazamiento_max_mm'):g} mm ← VIGENTE")
            rule["tabla"] = filas
        if es_grupo and res.get("hipotesis"):
            # lo que un ingeniero lee ANTES de firmar (bonded/lineal, exclusiones,
            # alcance acotado, nota del analista) → bloque «HIPÓTESIS Y ALCANCE»
            rule["hipotesis"] = res["hipotesis"]
        if res.get("estado") == "error":
            rule["recomendacion"] = "Refuerza la pieza crítica o reduce la carga (FS < 1.2)."
        rules.append(rule)
    return rules
