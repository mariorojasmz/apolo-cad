"""Mixin del CONTRATO DE INTEGRIDAD del documento (V6.1): `check_integrity`.

Sale de `document.py` (plan partir-nucleo-congelado, F5). Lee `resolve_all` por el módulo
`apolo.doc.document` EN CADA LLAMADA (import dentro del método): los tests lo reasignan ahí
(`docmod.resolve_all`) y una copia capturada aquí no vería el parche.
"""

from __future__ import annotations

from apolo.commands.state import RegenState
from apolo.doc import carril
from apolo.doc.persistencia import _CID_RE


class IntegridadDocumento:
    # ------------------------------------------------- contrato de integridad (V6.1)
    def check_integrity(self) -> list[str]:
        """Verifica los INVARIANTES del documento y devuelve una lista de violaciones,
        cada una un string ACCIONABLE (lista vacía = íntegro). Es READ-ONLY PURO: no
        muta el documento ni ninguna caché, y NUNCA lanza (cualquier fallo interno se
        reporta como violación). Una entrada con prefijo ``"degradado: "`` NO es un
        error de corrección: solo señala pérdida de instancing (definición desalojada
        de DEFINITIONS) que el fallback de render ya cubre — el modo estricto la ignora."""
        from apolo.commands.registry import DEFINITIONS
        from apolo.doc.document import resolve_all  # D2: el de document, en cada llamada

        issues: list[str] = []
        log_ids = {c["id"] for c in self.commands}

        def _cmd_alive(cid: str) -> bool:
            # command_id directo del log, o sintético '{cmd}_{orig}' de insert_project
            # cuyo prefijo (el comando anfitrión) sigue vivo
            return cid in log_ids or cid.split("_", 1)[0] in log_ids

        # features: id coherente, comando vivo, contrato de instancia (mesh_key⇔matrix)
        for fid, feat in self.scene.items():
            if feat.id != fid:
                issues.append(f"la feature '{fid}' guarda id interno '{feat.id}' (deben coincidir)")
            if not _cmd_alive(feat.command_id):
                issues.append(
                    f"la feature '{fid}' apunta al comando '{feat.command_id}', ausente del log"
                )
            if (feat.mesh_key is None) != (feat.matrix is None):
                issues.append(
                    f"la feature '{fid}' tiene instancia a medias "
                    f"(mesh_key={feat.mesh_key!r}, matrix={'set' if feat.matrix else None})"
                )
            elif feat.mesh_key is not None and feat.mesh_key not in DEFINITIONS:
                issues.append(
                    f"degradado: la feature '{fid}' referencia la definición '{feat.mesh_key}', "
                    "desalojada de DEFINITIONS (el render usa el shape mundial: solo se pierde instancing)"
                )

        # conectividad: toda referencia a una feature/junta debe existir
        for jname, j in self.joints.items():
            for ref in (j.get("parent"), j.get("child")):
                if ref not in self.scene:
                    issues.append(f"la junta '{jname}' referencia el sólido '{ref}', ausente de la escena")
        for mname, m in self.mates.items():
            for ref in (m.get("feature_a"), m.get("feature_b")):
                if ref not in self.scene:
                    issues.append(f"el mate '{mname}' referencia el sólido '{ref}', ausente de la escena")
        for cname, con in self.constraints.items():
            if con.get("joint") not in self.joints:
                issues.append(f"la restricción '{cname}' referencia la junta '{con.get('joint')}', ausente")
        for fname, f in self.fasteners.items():
            for ref in (f.get("a"), f.get("b")):
                if ref not in self.scene:
                    issues.append(f"el fijador '{fname}' referencia el sólido '{ref}', ausente de la escena")
        for gname, g in self.grounds.items():
            if g.get("feature") not in self.scene:
                issues.append(f"el anclaje '{gname}' referencia el sólido '{g.get('feature')}', ausente")

        # grupos: parent declarado + sin ciclos. La membresía es TOLERANTE por diseño
        # (un member cuyo comando se borró se reporta vía missing_members, no aquí).
        for gname, g in self.groups.items():
            parent = g.get("parent")
            if parent is not None and parent not in self.groups:
                issues.append(f"el grupo '{gname}' cuelga del padre '{parent}', que no existe")
            seen: set[str] = set()
            cur = gname
            while cur is not None:
                if cur in seen:
                    issues.append(f"el grupo '{gname}' forma un ciclo de parents")
                    break
                seen.add(cur)
                nxt = self.groups.get(cur)
                cur = nxt.get("parent") if nxt else None

        # caché de regeneración incremental (blindaje del fix B), indexada sobre la ESCENA
        n = carril.n_escena(self.commands)
        if len(self._regen_sigs) != n:
            issues.append(f"_regen_sigs tiene {len(self._regen_sigs)} firmas para {n} comandos")
        for k, st in self._regen_ckpts.items():
            if not isinstance(k, int) or not (0 <= k < n):
                issues.append(f"checkpoint con clave inválida {k!r} (fuera de [0,{n}))")
            elif not (isinstance(st, RegenState) and isinstance(st.scene, dict)):
                issues.append(f"checkpoint {k} mal formado (se esperaba un RegenState con escena dict)")

        # seq monótono: nunca por debajo del mayor id c-numérico del log (evita colisiones)
        max_suffix = 0
        for cid in log_ids:
            mo = _CID_RE.match(cid)
            if mo:
                max_suffix = max(max_suffix, int(mo.group(1)))
        if self._seq < max_suffix:
            issues.append(f"_seq={self._seq} es menor que el mayor id del log (c{max_suffix})")

        # variables resueltas coherentes con las crudas
        try:
            expected = resolve_all(self.variables_raw)
        except Exception as exc:  # variables circulares/inválidas: ES una violación
            issues.append(f"las variables del proyecto no resuelven: {exc}")
        else:
            if expected != self.variables_resolved:
                issues.append("variables_resolved no coincide con resolve_all(variables_raw)")

        # dedup conservando orden (varias referencias pueden apuntar a lo mismo)
        out: list[str] = []
        for msg in issues:
            if msg not in out:
                out.append(msg)
        return out
