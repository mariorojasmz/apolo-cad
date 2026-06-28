# Marco de puerta plegable — Hoja de fabricación (UNIÓN ATORNILLADA)
Material: **madera tornillo**. Unidades: **mm**. Generado desde el modelo Apolo (geometría verificada).
Uniones: **junta a tope + tornillo + cola** (sin espiga). Las jambas son los postes; dintel y travesaño van encajados a tope entre ellas; los parteluces a tope entre dintel y travesaño.

## 1) Lista de corte
| Marca | Pieza | Cant | Sección | Largo |
|---|---|---|---|---|
| P1-IZQ | Jamba izquierda | 1 | 70×70 | **2500** |
| P1-DER | Jamba derecha | 1 | 70×70 | **2500** |
| P2 | Dintel (cabezal) | 1 | 70×70 | **2010** |
| P3 | Travesaño | 1 | 70×70 | **2010** |
| P4 | Parteluz (montante de ventana) | 3 | 50×42 | **309** |

Madera 70×70 ≈ **9.0 m** lineales · Parteluz 50×42 ≈ **0.93 m**. Pide ~2–3 cm de más por pieza para escuadrar las puntas y cortar al largo exacto.

## 2) Tornillería
| Unión | Tornillo | Cant | Por qué |
|---|---|---|---|
| ESQUINA (riel↔poste) | **Ø6 × 100 mm** avellanado | **2 por esquina = 8** | atraviesa la jamba (70) y entra ~30 en la testa del riel |
| PARTELUZ (montante↔riel) | **Ø4.5 × 90 mm** avellanado | **1 por extremo = 6** | atraviesa el riel (70) y entra ~20 en la testa del parteluz |

**Total: 14 tornillos** + **cola** (PVA/carpintero) en cada junta — la cola hace el grueso, el tornillo aprieta mientras seca.

## 3) Dónde van los tornillos (taladros marcados — ver planos por pieza)
- **Esquinas**: los 2 tornillos entran por la **cara EXTERIOR de la jamba** (la que va contra el muro), horizontales, en pareja **vertical separada 30 mm**, centrados en el riel.
  - En la jamba (datum = pie): esquina del **travesaño** a z=**2071 y 2101**; esquina del **dintel** a z=**2450 y 2480**.
- **Parteluces**: 1 tornillo por extremo, **por la cara exterior del riel** (dintel por arriba, travesaño por abajo), hacia la testa del parteluz, en **x = −503 / 0 / 503**.

## 4) Cómo atornillar (madera tornillo raja — pre-taladrar SIEMPRE)
1. **Pre-taladro en 2 pasos**:
   - Tornillo Ø6: broca **Ø4** (guía, en la pieza de la testa) + broca **Ø6.5** (paso, en la jamba) + **avellanado** para la cabeza.
   - Tornillo Ø4.5: broca **Ø3** (guía) + **Ø5** (paso) + avellanado.
2. **Cola** en la cara de la junta antes de apretar; limpia el sobrante.
3. En esquina, **2 tornillos** (evita que la junta pivote). Para más agarre en la testa (flojo a contra-veta): puedes **angular** un poco el tornillo o meter una **clavija Ø8 + cola** además.
4. Aprieta sin pasarte (la madera blanda se "barrena" si fuerzas); si una cabeza patina, sube un diámetro.

## 5) Galce del vidrio — REBAJE + JUNQUILLO
Vidrios de la ventana: **8 mm**, 4 paños entre los parteluces. Acristalado por **rebaje + junquillo** (vidrio desmontable por la cara de habitación).

**Rebaje** (perímetro interior de cada paño: cara inferior del dintel, cara superior del travesaño, caras laterales de jambas y parteluces, en el tramo z=2121–2430):
- Profundidad hacia dentro del miembro: **10 mm**. Ancho (aloja el canto del vidrio): **9 mm** (vidrio 8 + 1 de holgura). Se hace en la **cara de habitación** (la del junquillo); en los parteluces, en **ambos** lados. El rebaje queda **libre de los tornillos** (estos van en las testas, fuera del tramo de ventana).

**Vidrio** (corte del cristalero): cada paño = **luz del hueco + 16 mm** en ancho y alto. Paños ≈ 452×309 → cristal ≈ **468×325 mm** (×4, confirmar luz real por paño).

**Junquillo**: sección **12 × 10 mm**, madera tornillo; largo total ≈ **6.1 m** (4 paños × ~1.52 m), a inglete en esquinas.

**Orden de ensamble**: armar y atornillar+encolar el marco → colocar cada vidrio → clavar el junquillo.

> Nota de modelo: el galce está **especificado y acotado** (esta sección); aún NO está cortado en el 3D (cambio coordinado grande). El comando **`rebaje`** ya está en Apolo para hacerlo cuando se quiera.
