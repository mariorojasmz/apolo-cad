---
estado: en curso
nota: contrato APROBADO por Mario (2026-10-30, «Apruebo»); F0 hecha (Bitácora, D1–D8 ajustadas); falta F1–F6
descripcion: La puerta juzga bien la madera, el plástico, el tornillo y la viga que no salen del catálogo, en vez de rechazarlos por no saber leerlos o aprobarlos sin mirarlos
---

# La puerta juzga bien lo que no sale del catálogo

## Estado y origen

Pedido de Mario (2026-10-30), después de una tanda de 15 máquinas en la laptop: «¿tienes mejoras
para la puerta, apolo core, apolo pro o mcp?» y, con la lista ajustada a la puerta v31,
«Sí, escríbelo». Lo enmarcan dos reglas suyas: la calidad va en código determinista, no en la
memoria del agente ([calidad en piedra](hallazgos-del-revisor-en-la-puerta.md) § Estado y origen),
y la regla es general, no de una familia de máquinas.

Evidencia: 15 pilotos modelados con la receta de pilotos (modelado → revisor a ciegas → puerta →
hasta 3 rondas de corrección → re-revisión a ciegas), cerrados con la puerta v24 y re-evaluados
con la v31 (`main` 5d4f6bc2, sin tocar los modelos):

- 9 pilotos máximos de familias de madera, inox y acero (mesas inox con y sin poza, mesas de
  soldadura Ø16 y Ø28, mesa de bolas, mesa plegable, silla plegable alta, escalera de 7 peldaños,
  estantería de 2 m) y 6 mínimos nuevos (tres mesas de trabajo, carro de tres niveles, estructura
  de paneles solares sobre techo, transportador de rodillos con cadena soldado);
- con v24, 12 de 15 con la puerta APROBADA y 4 convergidas; con v31, **3 de 14 aprueban** (la de
  paneles quedó sin veredicto por la API, se repite en la F0);
- en las 15, el revisor a ciegas cerró con 0 ALTA y 1 a 5 MEDIA en las que no convergieron; las
  rondas de corrección y re-revisión fueron el 63 % de los 259,5 USD del lote.

## El problema / lo que hay hoy

Lo que la puerta no sabe leer lo rechaza, y lo que no sabe medir lo aprueba. Agrupado por modo de
falla, con lo visto en las 15 y el código de `main`:

1. **Un producto de madera o plástico que la tabla no conoce no se puede declarar bien.**
   `bom.comprable` FALLA en 9 de las 14 con v31 por «madera … sin norma ni clase resistente»
   (`library/bom_comprable.py:53-55`). La tabla de materiales no tiene contrachapado, triplay,
   MDF, HDF, OSB, PU ni PC (`library/materials.py`, claves: acero, inox, aluminio, latón, zinc,
   copaiba, haya, radiata, eucalipto, madera, vidrio, pvc, caucho, cartón, concreto, acetal,
   PE, PP, PA): un «contrachapado fenólico EN 314-2» pesa y resiste como «madera» genérica y el PU
   se lee como PVC. La clase resistente se acepta sólo de EN 338 / EN 14080 escrita en el material
   (`library/bom_compra.py:72-78`); la norma peruana de madera estructural (RNE E.010, grupos A/B/C)
   no la reconoce el patrón (`_NORMA_MADERA_RE` pide dígitos tras la sigla), y la copaiba, especie
   tabulada, no trae ninguna clase con fuente.
2. **El tornillo que no es un perno hexagonal se mide como si lo fuera.**
   - una pieza a medida con «tornillo» en el nombre sale `perno` (`services/calidad_pernos.py:76-79`)
     y `largos_perno.ref_para` la busca como PERNO-M (`library/largos_perno.py:64-68`): la
     estantería tiene `union.largo_comercial` en FALLA (40 de 146) por tornillos de madera;
   - una cabeza sin hexágono (Torx, Pozidriv, grapa de panel solar) sale SIN_EVALUAR en
     `union.acceso_herramienta` (`library/calidad/acceso_herramienta.py:249-251`): 106 en la
     estantería, 12 en la estructura de paneles; SIN_EVALUAR no se puede justificar;
   - el catálogo de tornillo de madera tiene 4 tirafondos sin norma ni tipo de huella
     (`library/data/103_tornilleria_madera.yaml`); el DIN 571 hexagonal ya existe
     (`113_tirafondos_hex.yaml`).
3. **La pieza se clasifica por cualquier palabra del nombre, no por su rol.**
   `es_nombre_de_tornilleria` y `_TUERCA_RE` buscan en todo el nombre (`library/lints.py`,
   `services/calidad_pernos.py:30,77`): «Arandela de perno …» cuenta como tornillería, un pie
   nivelador con «espárrago» en la descripción se mide como perno, y un «Eje» que no gira cuenta
   como peligro de parte móvil (`library/seguridad/peligros.py:58-70`). `roles.rol_union` ya va
   por el rol (`services/roles.py:23-46`): el resto no.
4. **Una interferencia grande pasa si hay una unión declarada entre las dos piezas.** Silla
   plegable (re-revisión, ALTA): 9 903 mm³ entre travesaño y pata, y la puerta aprobó. El par con
   `fasten` se excluye entero, sin tope de volumen (`services/delivery_inputs.py:31`), y
   `union.contacto_real` sólo pide que se toquen.
5. **La estructura que no es un perfil cortable de catálogo no se calcula.** Flecha y pandeo
   dan NO_APLICA a un tablero, un montante de madera o un tubo de `run_script`: `_candidata` exige
   `comp.cuttable` y `familia` (`services/vigas_rules.py:104-106`) y las columnas sólo reconocen 5
   familias de perfil (`services/columnas_rules.py:30,69`). `estructura.flecha` sale NO_APLICA en 9
   de 12 máquinas de la tanda y el revisor lo nota en unas 10 («engineering_check vacío»). La F0
   de [hallazgos-del-revisor](hallazgos-del-revisor-en-la-puerta.md) (Bitácora, límites) lo mandó a
   un plan propio que no se escribió.
6. **El vuelco sólo mira que el centro de gravedad caiga en la base**
   (`library/engineering/report_estructura.py:170-217`): no suma la fuerza horizontal de trabajo
   ni la carga en el borde que los requisitos sí declaran. En la mesa de ensamble el revisor halló
   un vuelco ALTA («se cae a partir de ≈ 202 N») que la puerta había aprobado; 11 de 12 modeladores
   hicieron la cuenta a mano. Está en `docs/backlog.md`.
7. **Lo que cuelga de una copia de patrón no sigue a las variables.** `fasten` ya acepta la raíz
   y los conjuntos (`commands/exec_uniones.py:100-113`), pero `ground`
   (`commands/exec_ensamblaje.py:190-196`), `add_joint` y `set_justifications`
   (`services/puerta_publicacion.py:160-165`) no; material y color se guardan por pieza
   (`doc/metadatos.py:62-78`) y `_exec_pattern` no los copia (`commands/exec_basicos.py:78-83`). En
   6 máquinas, subir N o L dejó copias sin material, sin apoyo o sin justificación: la variante
   deja de salir «cambiando sólo las variables».

## Lo que se revisó antes de escribir esto

- La lista salió de 55 reportes de modelado y corrección y 55 de revisión a ciegas de las 15
  máquinas (`C:\t\maq\<slug>\`), cruzada ítem por ítem contra `main` 5d4f6bc2: lo que el registro v25–v31 ya
  resolvió no entra (copias de patrón que heredan el número de su raíz en `sobrantes`, `fasten`
  con conjuntos, distancias en madera, higiene, `bom.comprable`, compra por su nombre).
- `wip/normas-en` (registro v32) sólo enseña a reconocer siglas EN/IEC/ASTM/UNE/JIS/NTP en la
  norma de compra: no agrega materiales ni clases. Se integra antes que este plan y no se repite.
- Pie nivelador (contratuerca, carrera real, rosca enganchada) y productos plegables (juntas no
  declaradas, sobre-centro) se repiten en 4 y 3 máquinas, pero cada uno pide su propio análisis
  de mecanismo: van con plan aparte.
- La oreja del portamotor de `create_roller_conveyor` (e = 16,02 < 16,5 mm = 1,5·d0 con d0 = 11)
  es un defecto de una plantilla, no de la puerta: va como fix directo (`OREJA_U` fija en
  `library/rodillos_cadena_motriz.py:48-52`).

## Decisiones (para vetar)

- **D1. La tabla de materiales gana los productos que el mercado vende con norma**: contrachapado
  y triplay (EN 636), MDF (EN 622-5), HDF, OSB (EN 300), tablero fenólico, PU (poliuretano, deja de
  leerse como PVC), PC (policarbonato) y el latón con su designación (CuZn39Pb3, EN 12164 / ASTM
  B16). Cada uno con densidad y resistencia de fuente citada en el código, como las maderas de D2
  de hallazgos-del-revisor. Las especies se buscan ANTES que el genérico (regla actual de `_norm`).
  *Ajuste F0*: se suman **cobre** y **EPDM**; el PRODUCTO se busca antes que la especie
  («contrachapado de copaiba» es contrachapado, no copaiba maciza); el HDF no tiene fuente y no se
  tabula hasta tenerla. `bom.comprable` lee la norma de la madera también del NOMBRE de la pieza,
  como ya lo hace el metal (`norma_de_material`).
- **D2. La clase resistente de la madera también se acepta por la norma peruana**: «grupo A/B/C
  (E.010)» del RNE, además de EN 338 / EN 14080. Para las especies tabuladas (copaiba, pino
  radiata, eucalipto, haya) la tabla trae la clase con su fuente cuando la fuente existe; si no
  existe, no se inventa: el material la tiene que escribir quien modela y la FALLA queda. Porqué:
  Apolo modela madera de Lima y el comprador de Lima compra por grupo E.010, no por EN 338.
  *Ajuste F0*: copaiba → **Grupo C** (E.010 Anexo 1, sólo *Copaifera officinalis*; la nota lo
  dice); el grupo D (nuevo en 2021) también se acepta. Pino radiata y haya NO llevan clase por
  defecto: su clase EN depende del grado visual (UNE 56544, AGR-VISUAL), así que la escribe quien
  modela; eucalipto, sin fuente. La designación propuesta (E.010 no fija formato; Art. 11.5 pide
  grupo y contenido de humedad en planos): «copaiba, Grupo C (E.010), CH ≤ 22 %».
- **D3. El tipo de tornillería sale del rol y de la ficha, no de cualquier palabra**: una pieza a
  medida es `perno` sólo si su ROL (`piece_role`, la cabeza del nombre) es perno/tornillo de
  máquina/espárrago; «tornillo para madera», «tirafondo», «autorroscante» → `madera`; y la tabla de
  largos comerciales usa la serie de su tipo (madera: la serie de EN 14592 / DIN 7997). Lo mismo
  para `_TUERCA_RE`, `es_nombre_de_tornilleria` y el peligro de «eje»: por rol. *Ajuste F0*: la
  norma después del complemento («Arandela ancha del tablero DIN 9021») no se corta en `cabeza()`.
- **D4. El acceso de herramienta se evalúa por la impronta, no sólo por el hexágono**: Torx,
  Pozidriv/Phillips, Allen y ranura llevan destornillador o punta en línea con el eje (holgura
  = largo de la punta + mano, con su fuente: ISO 10664 / ISO 4757); una grapa o fijación de
  sistema se evalúa por su llave declarada en la ficha. Lo que no tiene impronta ni llave
  declarada sigue SIN_EVALUAR, pero ahora **justificable** con la herramienta escrita.
  *Ajuste F0*: el largo de la llave Allen sale de ISO 2936 y el de la punta PH/PZ de ISO 8764-2
  (no ISO 4757); Torx no tiene largo normalizado (ISO 10664 es sólo la impronta) y la holgura de
  mano tampoco: van como criterio de diseño, escrito como tal en el código. La tuerca martillo, la
  de barril y el inserto roscado se evalúan por la cabeza del perno con el que trabajan (eran 20
  de los SIN_EVALUAR de la estructura de paneles, no la grapa).
- **D5. El catálogo de tornillo de madera pasa a familia**: EN 14592, cabeza avellanada con
  huella TX y PZ, Ø 3–6 × 16–80 mm (la serie comercial), con norma, huella y carga característica
  de arranque. Los 4 TIRAFONDO-* actuales quedan (ids estables) con su norma completada.
  *Ajuste F0*: los largos por diámetro siguen una serie real de ETA (Ø3: 15–45; Ø3,5: 16–55;
  Ø4 y Ø4,5: 20–80 de 5 en 5 sin 75; Ø5: 20–120; Ø6: 20, 30–300); la ficha guarda f_ax,k y ρa,
  no una carga fija: EN 1995-1-1 ec. 8.38–8.39 vale sólo para 6 ≤ d ≤ 12 y bajo Ø6 se usa el
  f_ax,k declarado corregido por (ρk/ρa)^0,8 (ec. 8.40a).
- **D6. Una unión declarada no tapa una interferencia de volumen**: entre piezas que no son
  tornillería, un par con `fasten` cuyo volumen común supera la tolerancia de la puerta
  (`EXCESS_TOL_MM3`, la misma de los pares no declarados) FALLA en
  `interferencia.sin_colision`. Contacto, soldadura y encolado son caras que se tocan, no
  volumen compartido. *Ajuste F0*: ese ítem no existe (la interferencia vive en
  `entrega.semaforo`); el nuevo se llama `union.interferencia_declarada`. La rosca engranada no
  cuenta: un pie nivelador en su placa roscada (565,5 mm³) o un espárrago en su tuerca soldada
  (457,7 mm³) son volumen intencional y entran a los tests como casos que NO fallan.
- **D7. Flecha y pandeo calculan la pieza estructural que no es de catálogo, con la sección de
  su geometría**: rectángulo macizo (tablero, montante, travesaño de madera) y tubo rectangular
  o redondo (`run_script`, `create_sheet_metal` cerrado) se reconocen por la caja orientada y la
  sección constante a lo largo del eje; el material da E y la resistencia (D1, D2). Lo que no
  tiene sección constante reconocible sale **SIN_EVALUAR justificable**, nunca NO_APLICA en
  silencio. Criterio de flecha: el de hoy de `vigas_rules` para el metal y EN 1995-1-1 § 7.2
  para la madera, con la cláusula citada en el código. *Ajuste F0*: la madera por grupo E.010 se
  calcula con SUS esfuerzos admisibles y el **E mínimo** del grupo por elemento (Art. 17: el
  promedio sólo en acción de conjunto; grupo C: 5 394 MPa, no el E de la tabla de materiales); la
  de clase EN, con EN 1995-1-1: nunca se mezclan admisibles con kmod/γM. E del contrachapado: EN
  12369-2 o la ficha del fabricante. La plancha perforada sale SIN_EVALUAR justificable: dos
  máquinas aprobadas hoy pasan a pedir justificación (se cuenta en la F6).
- **D8. El vuelco suma lo que declaran los requisitos**: con fuerza horizontal de trabajo y
  carga de borde en `set_requirements`, `estructura.vuelco` compara el momento estabilizador con
  F_h·h + la carga de borde en la arista más desfavorable, coeficiente 1,5 (EN 1990 para acción
  variable desfavorable). Sin esos requisitos, sigue como hoy y lo dice. *Ajuste F0*: las claves
  no existen en `requisitos.NUMERICAS` y se crean; se usa EN 1990 Tabla A1.2(A) completa (peso
  propio estabilizante ×0,9, desestabilizante ×1,1, variable desfavorable ×1,5, la favorable en 0:
  el caso que el revisor halló fue la mesa VACÍA). Ninguna de las 15 declara esas cargas: D8 no
  cambia nada en la F6 sin re-hacer una máquina que las declare.
- **D9. La raíz de un patrón es ciudadana**: `ground`, `add_joint` y `set_justifications`
  aceptan la raíz de un patrón (o un conjunto), y `set_material` / color de la raíz los heredan
  las copias, también las que nacen al subir la variable (metadato por comando, no por pieza:
  [doc](../../core/apolo/doc/CLAUDE.md) § Metadatos de manifest). Una copia con material propio lo
  conserva.
- **D10. Cada fase que cambia lo que la puerta decide sube el registro** (v33, v34, …) con su
  línea en `historial_registro.py`; una máquina aprobada con un registro anterior vuelve a correr
  la puerta antes de publicarse (regla de hoy).

## Alternativas descartadas

- **Aflojar `bom.comprable` para la madera** (aceptar «copaiba» pelada): la regla existe porque
  el revisor marcaba compras que no se podían hacer (D4 de hallazgos-del-revisor); el problema es
  que el modelador no tiene cómo declararla bien, no que la regla pida de más.
- **Pedir al modelador que dibuje la impronta del tornillo**: geometría que no mejora el
  entregable y que la puerta igual tendría que reconocer; la ficha de catálogo ya la dice.
- **Calcular la madera con FEA**: el FEA estático existe, pero es caro por pieza y la flecha de una
  viga de sección constante sale exacta con la fórmula; el FEA queda para lo que no es viga.
- **Una regla de vuelco con fuerza fija** (p. ej. 200 N siempre): una mesa de empaque y un rack no
  se empujan igual; la fuerza la declara el requisito.

## Fases

- **F0 — medir** (sólo lectura, S). Hecha (Bitácora). Puerta v32 (con `wip/normas-en` integrada) sobre las 15
  máquinas (incluida la de paneles); tabla por ítem; las piezas de cada máquina que caen en los
  modos 1–7, para los tests de cada fase; fuentes de clase resistente de copaiba, pino radiata,
  eucalipto y haya (EN 1912, RNE E.010 Anexo, Junta del Acuerdo de Cartagena) y de los
  productos de D1. Ajusta D1–D9 si la medida lo pide (vetable).
- **F1 — materiales y clase de la madera** (`library`, M). D1, D2 + tests. Registro +1.
- **F2 — tornillería por rol e impronta** (`library`, `services`, M). D3, D4, D5 + tests.
  Depende de F1 sólo por el material de la tornillería de latón. Registro +1.
- **F3 — interferencia que no se tapa** (`services`, S). D6 + tests. Registro +1.
- **F4 — estructura fuera de catálogo** (`services`, `library/engineering`, L). D7, D8 + tests.
  Depende de F1 (E y resistencia de los materiales nuevos). Registro +1.
- **F5 — la raíz del patrón** (`commands`, `doc`, `services`, M). D9 + tests de replay (un log
  viejo regenera igual: el metadato por comando entra con el default de hoy). Si toca la caché de
  geometría, decidir versión o epoch (raíz § Log de comandos).
- **F6 — verificar** (S). Puerta del último registro sobre las 15; comparación con la F0 por
  ítem; 2 máquinas de madera re-hechas desde el encargo con la receta, para ver si bajan las
  rondas (la F7 de hallazgos-del-revisor midió que bajar los hallazgos que mide la puerta no basta
  si quedan los que no mide: se reporta igual).

F1–F3 son independientes entre sí (máximo 2 agentes a la vez); F4 espera a F1; F5 no depende de
ninguna.

## Lo que este plan NO hace

- Pie nivelador y productos plegables: planes aparte (ver «Lo que se revisó»).
- La oreja del portamotor de `create_roller_conveyor`: fix directo con su `version` del
  `CommandSpec`.
- Normas por mercado en toda la BOM (designación EN del acero en vez de ASTM según dónde se
  vende): el núcleo no tiene hoy la noción de mercado del proyecto; queda para cuando un
  requisito la declare.
- Corregir las máquinas de la tanda: eso es producción, con la receta, después de la F6.

## Riesgos

- **Máquinas aprobadas que dejan de aprobar** (D6, D7, D8 miden lo que hoy no se mide): es lo
  buscado; la F0 da el antes y la F6 el después por máquina, y cada umbral queda vetable.
- **Fuentes de clase resistente que no existen para una especie** (copaiba): D2 no inventa; la
  FALLA queda y el material la escribe quien modela con su fuente.
- **D7 reconoce mal una sección** (pieza con agujeros, chaflanes): si la sección no es constante
  sale SIN_EVALUAR justificable; los tests incluyen tablero perforado y tubo con tapas.
- **D9 cambia cómo se guardan material y color**: un `.apolo` viejo tiene que abrir igual; el
  test de replay de proyectos testigo es el gate.

## Bitácora

### F0 — medir (2026-10-30)

**Puerta v32** (`main` 9ce35728) sobre las 15 máquinas, sin tocar los modelos: aprueban **3 de
15** (mesas de soldadura Ø16 y de bolas, carro de tres niveles; la de paneles ya tiene veredicto).
Ítems en FALLA o SIN_EVALUAR:

| ítem | máquinas | modo |
|---|---|---|
| `bom.comprable` FALLA | 12 de 15 | 1 (madera, latón) y compras sin designación del modelo |
| `union.distancia_al_borde` FALLA | 5 (estantería, escalera, mesa plegable, silla, rodillos) | defectos reales; en rodillos, la oreja |
| `union.acceso_herramienta` SIN_EVALUAR | 2 (estantería 106, paneles 20) | 2 |
| `movimiento.coherente` FALLA | 2 (escalera, mesa plegable) | plegables: plan aparte |
| `union.largo_comercial` FALLA | 1 (estantería, 40 de 146) | 2 |
| `union.contacto_no_cuelga` FALLA | 1 (desagüe de la mesa con poza) | del modelo |

Por modo (las piezas de cada máquina, para los tests de cada fase, en el reporte de la F0):

1. Madera sin clase: **7 de 14** (no 9): calzos, entrepaños, tableros y repisas de «madera»,
   peldaños, travesaños y tarugos de copaiba; dos tableros escriben «contrachapado fenólico EN
   314-2» en el NOMBRE y la puerta no lo lee (ajuste de D1). Latón sin grado en **2**: un inserto
   roscado y un conductor de tierra de cobre que el modelador declaró latón porque «cobre» no
   está; un sellador de PU se pesa como acero.
2. Tornillo de madera medido como perno («PERNO-M3×29.6 no está en el catálogo»): la estantería.
   En paneles, lo SIN_EVALUAR es la **tuerca martillo**, no la grapa (ajuste de D4).
3. Por palabra: el espárrago del pie nivelador medido como perno, un «Eje» que no gira como parte
   móvil, una «Correa» de paneles leída como transmisión, una arandela «de perno» como tornillería.
4. La silla (9 903 mm³ entre travesaño y pata) ya se corrigió en la ronda 2: el test usa una
   fixture con el par, no la máquina.
5. `estructura.flecha` NO_APLICA en **10 de 15**: tubos inox, planchas, copaiba y las vigas L de
   paneles (van inclinadas: hipótesis a confirmar en la F4).
6. Mesa de ensamble: el centro de gravedad «se cae a partir de ≈ 202 N» con la mesa vacía hacia
   atrás; mesa Ø16 a 1000×800: 660 contra 675 N·m.
7. Copias sin material (mesa inox), `set_justifications` sobre una copia («pieza inexistente»),
   `ground` y material sobre copias (mesa Ø28), `add_joint` sobre una copia (escalera).

**Fuentes leídas** (cifra verificada en la fuente salvo donde se dice):

- RNE E.010 (2021): Anexo 1 (copaiba = Grupo C, sólo *C. officinalis*); Tablas 2, 3 y 5
  (admisibles del grupo C: fm 9,8; ft 7,3; fc∥ 7,8; fc⊥ 1,5; fv 0,8; Emín 5 394; Eprom 8 826 MPa;
  A: fm 20,6 / Emín 9 316; B: 14,7 / 7 355; D: 6,8 / 4 414); Art. 11.5 y 17.
- Pino radiata: UNE 56544 ME-1 → C24, ME-2 → C18 (CTE DB SE-M Tabla C.1; AGR-VISUAL 2024). Haya:
  H1 → D40, H2 → D35 (Francia), LS1 → D45 (Italia), AGR-VISUAL 2024. *E. globulus*: sin fuente
  primaria (D40 por UNE 56546 sólo en fuentes secundarias). El manual de la Junta del Acuerdo de
  Cartagena no se leyó.
- OSB/3 EN 300 (copia no oficial y fichas de fabricante); MDF EN 622-5 (ficha de fabricante);
  contrachapado fenólico EN 314-2 clase 3 (ficha de fabricante, 18 mm: Em 10 048, fm,k 40,2 MPa);
  PU de rueda 92–95 ShA, ρ 1,26; PC (ISO 527/178: ρ 1 200, E 2 400, σy 65 MPa); latón CW614N
  (EN 12164: ρ 8,47, E 97 GPa, R430). HDF: sin fuente.
- Herramienta: ISO 2936 (largo de la llave Allen), ISO 8764-2 (hoja PH/PZ); Torx sin largo
  normalizado.
- Tornillo de madera: EN 1995-1-1+A1 § 8.7.2 (ec. 8.38–8.40a) y una ETA de tornillo EN 14592
  (f_ax,k 14,0 N/mm² para d < 6 y la serie de largos de D5).

**Fuera del plan, visto en la medición** (no se arregla aquí):

- Defectos reales de diseño: borde de madera en estantería, escalera, mesa plegable y silla;
  compras sin designación del modelo (pie «o equivalente», laina, sifón, eje del reductor,
  autoperforante, varilla, regatón, taco); el desagüe de la mesa con poza que cuelga de un
  contacto. Son producción con la receta, después de la F6.
- `bom.comprable` le pide comprable a un elemento EXISTENTE del sitio (la cubierta sobre la que
  apoya la estructura de paneles): fix directo aparte.
- La oreja del portamotor de rodillos: fix directo en curso (no es de este plan).
