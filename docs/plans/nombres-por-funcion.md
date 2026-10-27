---
estado: implementado
nota: implementado y en GitHub (F0–F6, puerta v12); Mario juzgó «Mandos» en el visor (2026-10-27, «mucho mejor»); pendiente aparte: nombres de las máquinas ya hechas (tanque, elevador), la placa de leyenda en el 3D y el plano (backlog)
descripcion: cada mando, piloto y sensor se ve por lo que HACE («Marcha», «Tapa del tanque»), con la designación chica al lado, y la puerta de publicación no aprueba una máquina cuyos mandos no tienen nombre
---

# Nombres por función — «Veo qué hace cada botón sin abrir el plano»

Fuera del roadmap: es un subplan de la máquina viva (V8.4) y del tablero (V8.5).

**Aprobación**: D1–D18 las aprueba Claude con el criterio que le delegó el dueño, y quedan
vetables. Un veto se anota en la Bitácora y ajusta la fase que todavía no se lanzó.

## 1. Estado y origen

Lo pidió Mario el 2026-10-27. Abrió «Mandos» en la sesión viva de la mezcladora de paletas de
200 L y tuvo que preguntar qué hacía cada botón:

> «tienes que darle un nombre y descripción para saber lo que hace … no te digo que lo rellenes de
> texto, sé más como Apple, pero no entiendo cuando dice solamente -Q1, tendría que ver los planos
> para eso»

Lo quiere como REGLA al construir mandos, pilotos y otras herramientas, y quiere saber qué otras
superficies del visor tienen el mismo defecto.

Ampliación del mismo día: la regla es también un ÍTEM de la puerta de publicación, para que la
cumpla cualquiera que construya máquinas, en cualquier PC.

## 2. El problema (medido)

**Inventario completo**, superficie por superficie y por gravedad: en el [informe](nombres-por-funcion-informe.md) § 1, anexo de
este borrador. Lo esencial:

- **El dato no existe.**
  - `AddDeviceParams` (`commands/models_electrico.py:70-136`) y `Dispositivo`
    (`library/electrico/modelo.py:75-111`) no tienen campo de nombre.
  - El `inicio` de la sesión viva lleva `designacion, tipo, ref, color, pieza` por mando
    (`cosim/vivo_fotograma.py:62-76`) y por piloto (`:112`).
- **La UI pone la designación como lo principal y el TIPO genérico al lado:**
  - `vivo/PanelMandos.tsx:168-169`, con «también con clic en el 3D» repetido en las 8 filas;
  - pilotos: `:276-280`, «Piloto» en las cuatro filas;
  - lecturas: `vivo/lecturas.ts:76`, -K2 y -K3 iguales.

  En la mezcladora, -S1/-S2/-S3 se leen igual («Pulsador [Presionar]»), y lo mismo -P3/-P4.
- **El selector no muestra su posición.** `PanelMandos.tsx:245` la guarda en un `useState(null)`
  local, aunque el modelo la publica (`cosim/modelos/mandos.py:198-199`, `<des>.posicion`). Y
  «[0][I]» no dice manual o ciclo.
- **Una cosa, dos nombres.** El resguardo es «Resguardo» en Mandos (`vivo/mandos.ts:69`) e
  «Interruptor de resguardo» en «Simular falla» (`vivo/fallas.ts:50`). Hay tres tablas de nombres
  de tipo en la UI (`mandos.ts:64`, `fallas.ts:45`, `arbolSenales.ts:18`).
- **Códigos opacos en el resto:**
  - «Simular falla» ofrece «c160 · Cable» (`FallasVivas.tsx:100`; `services/cosim_red.py:231`);
  - el accionamiento manual dice «posición 14» (`neumatica/AccionamientoManual.tsx:42-54`);
  - el esquema dice «Regulador de caudal» ×2 y «Silenciador» ×3;
  - Tablero → Aparatos usa el nombre de CATÁLOGO como secundario (`services/tablero_panel.py:301`);
  - en «Pruebas», el título es el id del escenario y la descripción trae «c68_vastago»
    (`pruebas/VistaPruebas.tsx:65,102`);
  - las juntas se muestran por `name`: «c388_puerta» (`KinematicsPanel.tsx:194`, `EventosVivos.tsx:23`).
- **El nombre con sentido sólo existe a medias:**
  - el de la pieza de campo («Interruptor de tapa -B1», `c66`);
  - los comentarios del ST.

  Los aparatos de la PUERTA del tablero tienen pieza generada por `layout_tablero` con el nombre
  del catálogo («… · -S1 Pulsador Ø22 verde 1NA», `commands/tablero.py:156-157,194`). -S0, -S3 y
  -Q1 ni pasan por el PLC: el rearme va cableado `-S3:14 → -K2:S34` y `-K3:S34`.
- **Miente** (va primero, fix aparte): «El vástago de -MM1 pandea» con FS = 109. La frase de
  `services/neumatica_panel.py:137` no distingue el aviso «λ < 100 sin fy» del pandeo real
  (`library/neumatica/calculo.py:244-246`).

## 3. Lo que se revisó antes de escribir esto

- **`doc/carril.py:101-104`**: `layout_tablero` sólo lee `ref, designacion, ubicacion, cantidad,
  pieza` del `add_device`. Un campo nuevo fuera de `CAMPOS_LECTURA` no re-ejecuta el layout. Por
  eso NO se renombran sus piezas (D6).
- **`commands/electrico.py:40-49`**: `add_device` es del carril (`_exec_carril`). Sin huella nueva
  ni `version`, y sin `GEOM_CACHE_EPOCH`.
- **`tests/test_firma_dispositivo.py:122-136` y `services/escenarios.py:49`**: todo campo nuevo de
  `Dispositivo` decide entre firma y `FUERA_DE_FIRMA`.
- **`services/tablero.py:95-121`** (`piezas_en_tabla`, llamada en `api/routers/cosim_vivo.py:286`):
  el patrón para decorar el `inicio` en la API sin tocar el worker ni `COSIM_EPOCH`.
- **`library/calidad/registro.py`**:
  - `Entrada`: id, título, modo de falla, norma, familia, `aplica_si`, evaluar, elementos;
  - `hay(tipo)` sobre `hechos["elementos"]` (`services/puerta_hechos.py:140-158`);
  - `VERSION_REGISTRO = "11"` (`:82`);
  - FALLA bloquea y SIN_EVALUAR también.
- **`library/calidad/puerta.py:187` (`erc`)**: `riesgos.electrico` falla con cualquier aviso del
  ERC. Si la regla viviera en el ERC, una falta de nombre saldría como riesgo eléctrico (D8).
- **`library/calidad/justificadas.py`**: sólo avisos. El ítem nuevo es FALLA sin justificación.
- **`cosim/modelos/seguridad.py:83`**: `BORNES_ENTRADA` = S12, S22 (canales) y S34 (rearme). De ahí
  se derivan el grupo «Seguridad» y lo que rearma cada pulsador (D10, D11).
- **`commands/electrico.py:131-160`** (`prefijar`): `insert_project` copia los params del carril
  con su aspecto de función. El rótulo viaja solo, y la unicidad se mide por aspecto (D5).

## 4. Decisiones (para vetar)

- **D1. El nombre es un DATO declarado en `add_device`**: `rotulo` (≤ 30 caracteres, el texto de
  la placa de leyenda), `estados` (el nombre de cada posición o estado de SU ficha, validado
  contra el modelo en el evaluador, como `ajustes`) y `descripcion` (opcional, una frase,
  ≤ 100 caracteres).
  - Default `""`/`{}`: un log viejo regenera igual, sin upcaster. Se anota en `CAMPOS` de
    `tests/test_contrato_comandos.py`.
  - Porqué: lo que más importa (puerta del tablero, seguridad cableada) no tiene otra fuente, y es
    un ENTREGABLE (placa de leyenda; IEC 60204-1 § identificación funcional, numeral a confirmar
    en F0).
  - En el comando y no en el manifest: el `name` de las piezas y la designación ya viven en el
    log, `insert_project` lo copia solo y el undo sale gratis.
- **D2. Alcance**, sin pedir rótulo a lo que su tipo ya nombra:
  - **lo que se opera**: `MANDOS` + electroválvula con `manual`;
  - **lo que se lee**: piloto, hmi; y sensores (sensor, presostato);
  - **lo repetido** (dos del mismo tipo: relés, reguladores, cilindros): sólo aviso de
    `delivery_check`.

  El PLC, la fuente, el variador único, la bornera y la red se nombran por su tipo.
- **D3. Respaldo para MOSTRAR, nunca para APROBAR** (`services/rotulos.py`, una sola fuente):
  1. rótulo declarado;
  2. nombre de la pieza ligada que no generó un layout, sin designación ni prefijo;
  3. relé de seguridad → «Seguridad de» + los rótulos de lo que vigila (S12/S22);
  4. tipo de la ficha + su distintivo de catálogo («Pulsador verde»).

  Nunca la designación sola ni un id de comando. Cada fila lleva `origen`. El ST y las variables
  del PLC NO se muestran: sólo van como `sugerencia` en el caso de la puerta.
- **D4. Ítem `interfaz.nombres_por_funcion`** en `REGISTRO`:
  - `Entrada`, familia «seguridad»;
  - norma: «IEC 60204-1 §16.3 (a confirmar en F0) · criterio de diseño»;
  - `aplica_si = hay("operables", …)`, `elementos = "operables"`;
  - **FALLA sin justificación posible**: falta un dato que el modelador puede escribir;
  - SIN_EVALUAR si el carril no evalúa;
  - `VERSION_REGISTRO` "11" → "12", con su línea en el docstring.
- **D5. Criterio determinista** (`library/calidad/nombres.py`, puro). Detalle y tabla de ejemplos
  en el [informe](nombres-por-funcion-informe.md) § 2.5. Un rótulo vale si:
  - está declarado;
  - le queda una palabra de ≥ 3 letras al quitar designaciones, tokens de la ref y del `name` de
    la ficha, colores, números, medidas, códigos de contacto, conectores y una tabla CERRADA de
    nombres de tipo;
  - no trae `_`, `%`, `:` ni `c\d+`;
  - es único en su aspecto de función;
  - y, en un selector o una electroválvula manual, todas sus posiciones tienen nombre.

  La tabla de tipos no se abre para aprobar un rótulo.
- **D6. Las piezas del tablero NO se renombran**: `CAMPOS_LECTURA` no cambia. El rótulo se une al
  LEER (ficha de pieza, árbol, paneles). Renombrar re-ejecutaría el layout y lo que tiene detrás
  (40 comandos en la mezcladora) por un texto.
- **D7. Fuera de la firma y del worker**: `Dispositivo.rotulo/estados/descripcion` en
  `FUERA_DE_FIRMA`. El `inicio` se decora en la API (`rotulos_en_tabla`, junto a
  `piezas_en_tabla`): sin `COSIM_EPOCH`. Claves AGREGADAS al `inicio`: sin `version`.
- **D8. NO va en el ERC.** `delivery_check` suma la regla «nombres por función» (AVISO, con el
  mismo criterio de D5 más lo repetido de D2), en el bucle del modelador. `VERSION_BATERIA` sube.
  `riesgos.electrico` no la ve.
- **D9. Fila de mando**:
  - el rótulo manda (`--fw-medio`) y la designación va detrás, chica (`--fs-chico`, tinta
    secundaria);
  - un mando que SE QUEDA (seccionador, resguardo, selector) es un control SEGMENTADO con los
    nombres de sus estados, y el segmento marcado es el LEÍDO de la señal;
  - el pulsador con resorte y la seta siguen siendo botón con verbo;
  - la concordancia («Cerrada») la declara el modelador en `estados`; sin ellos, el default por
    tipo lo da el servidor (seccionador «Apagado/Encendido»).
- **D10. Un mando NUNCA se deshabilita por no tener efecto ahora.** El panel es un banco de
  prueba: «rearme con la tapa abierta no debe rearmar» es lo que se prueba. El rearme muestra al
  lado el estado de lo que rearma (los relés a los que va cableado), en palabras de su acción:
  «Falta rearmar» / «Rearmada». No usa «Corta la marcha»: junto a un botón, eso se lee como lo
  que el botón hace.
- **D11. Agrupar por propósito sólo con más de 5 mandos**, con regla derivada:
  - seccionador → Energía;
  - seta, resguardo y todo mando cableado a una entrada de relé de seguridad → Seguridad;
  - el resto → Operación.

  Después van Pilotos y Lecturas.
- **D12. Veredicto de «Mandos»** (pieza `Veredicto`): sólo hechos leídos de señales, en orden de
  bloqueo. Sin energía → parada de emergencia presionada → «<resguardo> abierto» → «La seguridad
  corta la marcha» → «Energía y seguridad habilitadas». Nunca «Lista para arrancar»: el permiso del
  PLC no se conoce.
- **D13. Una sola fuente de nombres** (servidor). Se borran las tablas de tipo de la UI
  (`mandos.ts:64`, `fallas.ts:45`, `arbolSenales.ts:18`) y «también con clic en el 3D» pasa a UNA
  `<Pista>` arriba.
- **D14. Pruebas**: título = `nombre` humanizado, derivado y sin campo nuevo. `set_scenario` avisa
  (no rechaza) una `descripcion` con ids de comando o pieza.
- **D15. Juntas** (Eventos, Cinemática): se nombran por su pieza HIJA; el `name`, secundario.
- **D16. `descripcion` sólo en la ⓘ (N2)**, nunca a la vista. Presupuesto de `ui/CLAUDE.md`.
- **D17. La BOM queda fuera**: es para comprar, la ref es su dato. Al backlog: Descripción
  primero y una columna de designaciones.
- **D18. Máquinas viejas**: FALLA en el ítem hasta declarar. La sugerencia (pieza, variable del
  PLC) va como texto en el caso y nunca se aplica sola. F6 completa la mezcladora y los testigos.

## 5. Alternativas descartadas

- **Derivar del ST**: comentarios libres que nombran dos aparatos o bornes («canal 1 tras -S0 y
  -B1», «-K2 33-34: rele…»); variables en jerga (`rs_ok`); y -S0/-S3/-Q1 no están.
- **Derivar del nombre de la pieza**: el layout las nombra por catálogo. Queda como respaldo para
  mostrar (D3).
- **Metadato en el manifest**: necesitaría copia propia en `insert_project` y undo aparte.
- **Dentro de `ajustes`**: se valida contra el `modelo` y entra a la firma.
- **Regla del ERC**: haría fallar `riesgos.electrico` por algo que no es eléctrico, y doble (D8).
- **Renombrar las piezas del layout**: re-ejecución por un texto (D6).
- **Un campo `genero`** para concordar estados: `estados` resuelve eso, los selectores y las
  válvulas.
- **Deshabilitar un botón sin efecto**: escondería la prueba (D10).
- **Marcar «sin nombre» en el visor**: castiga a quien mira por la omisión del modelador. La
  marca va a la puerta y a `delivery_check`.

## 6. Fases

### Antes de F1, fuera del plan: la frase que miente (HECHO, entró con el contrato)

**Fix directo, S, ~20 min.** `neumatica_panel._frase_memoria` dice «pandea» sólo con estado
«error». Con «aviso» por λ, dice lo que pasa: «Falta el límite elástico del vástago…». Lleva un
test con el aviso de la mezcladora.

### F0 — Medir (sólo lectura) · S · ~15 min

- Leer IEC 60204-1 § identificación funcional de mandos e indicadores y fijar edición y numeral
  (regla de citas: sin el texto leído, «criterio de diseño»).
- Contar, en la mezcladora y en cada documento de prueba con carril (`tests/data/tablero_piloto.json`,
  fixtures de `test_puerta_*`, testigos de `test_puerta_publicacion.py`), cuántos operables por
  tipo hay y cuáles caerían a FALLA.
- Correr el criterio de D5 sobre 30 rótulos reales y de ejemplo, en un script suelto. Ningún falso
  ✓ con nombres de catálogo; los falsos ✗ se anotan.
- Verificar que `<des>.posicion` llega en `textos` y que los lados de una electroválvula son las
  claves de `estados`.
- Medir el tamaño de `PanelMandos.tsx` (317 líneas) para planear el corte bajo 500.

Sale con ajustes A1…An a este contrato.

### F1 — El dato y el respaldo (backend) · M · ~55 min · depende de F0

**`commands/models_electrico.py`**:
- `rotulo`, `estados`, `descripcion`, con su description para el agente;
- su `pista` si cambia (`commands/pistas.py`).

**`library/electrico/modelo.py`**:
- campos de `Dispositivo` y `dispositivo_desde_ficha`;
- el evaluador del carril valida `estados` contra la ficha, con el error accionable que lista las
  claves válidas.

**`services/escenarios.FUERA_DE_FIRMA`** y `tests/test_firma_dispositivo.py`.

**`services/rotulos.py`** (dominio, lee un `Document`):
- `rotulo_de`, con la cadena D3 y su `origen`;
- `estados_de`, con los defaults por tipo;
- `grupo_de` (D11);
- `rearma_a` (S34);
- el nombre de un cable por sus extremos;
- el de una junta por su hija;
- el de un escenario humanizado.

Consumidores del servicio:
- `api/routers/cosim_vivo.py`: `rotulos_en_tabla` en el `inicio`, con `rotulo`, `origen`,
  `estados`, `descripcion`, `grupo` y `rearma` por fila de mandos, pilotos, dispositivos,
  válvulas, fallas y ramas;
- `services/tablero_panel.py` (aparatos, textos de calentamiento);
- `services/neumatica_panel.py` (símbolos, ítems, cilindros);
- `services/pruebas_panel.py` (título);
- `get_circuit`, que expone el rótulo.

**`design/guidelines.py`**: `corto`, `detalle` y `verificar` ([informe](nombres-por-funcion-informe.md) § 4). Golden del MCP: revisar
y `--congelar`.

**Gates** (pytest):
- `test_rotulos.py` nuevo, con la cadena y los defaults;
- `test_contrato_comandos.py` (CAMPOS);
- `test_firma_dispositivo.py`;
- `test_fotograma_contrato.py` (claves agregadas);
- `test_mcp_golden.py`;
- `test_pistas.py`;
- un log viejo de la piloto regenera byte a byte igual (`test_golden_regen.py`).

### F2 — La regla que obliga (puerta y entrega) · M · ~50 min · depende de F1

**`library/calidad/nombres.py`** (puro): el criterio D5 con su tabla cerrada; casos con
designación, motivo, piezas y `sugerencia`.

**`services/puerta_hechos.py`**: `elementos["operables"]` por tipo.

**`services/puerta_publicacion.py`**: el insumo `nombres`, filas de `services/rotulos.py`.

**`library/calidad/registro.py`**:
- la `Entrada` de D4;
- el id en la lista del docstring;
- `VERSION_REGISTRO = "12"` y su línea en «Qué cambió».

**`library/delivery.py`**: la regla «nombres por función» (AVISO, más lo repetido);
`VERSION_BATERIA` 3 → 4.

**`set_scenario`**: el aviso de ids en la descripción (D14).

**Gates**:
- `tests/test_puerta_nombres.py` nuevo:
  - cada fila ✓/✗ de la tabla de D5;
  - unicidad por aspecto (dos `insert_project` con «Marcha» pasan);
  - un selector sin `estados` falla;
  - NO_APLICA sin carril;
  - SIN_EVALUAR si el control revienta;
  - lo derivado no aprueba;
- `test_puerta_publicacion.py`, `test_puerta_f3.py` y `test_extensiones_f1d.py` con
  `version_registro` "12";
- los testigos públicos con su veredicto por ítem al día. El que tenga tablero declara sus rótulos
  en el fixture: no se relaja el ítem;
- `test_delivery.py`.

### F3 — «Mandos» (UI) · M · ~50 min · depende de F1 · en paralelo con F4

**`ui/src/vivo/`**:
- la fila (D9) en un componente propio, para que `PanelMandos.tsx` quede bajo 500 líneas;
- `Segmentado` para seccionador, resguardo y selector, leyendo `<des>.cerrado` / `<des>.posicion`;
- grupos (D11), veredicto (D12) y una `<Pista>`;
- ⓘ con `descripcion`;
- pilotos y lecturas con rótulo;
- «Simular falla» con rótulos (aparato, contacto, cable por extremos);
- la apertura con el escenario humanizado;
- se borran `NOMBRES` de `mandos.ts`, `TIPOS` de `fallas.ts` y lo que repite `lecturas.ts`;
- el muestrario con datos de la mezcladora: 8 mandos, 4 pilotos y 2 relés.

**Gates**: `npm test` (con `mandos.test.ts` y `fallas.test.ts` al día, `textoDeAyuda`,
`tuteoNeutro`, `tamanoArchivos`) y `npm run build`.

### F4 — El resto de las superficies (UI) · M · ~45 min · depende de F1 · en paralelo con F3

- `tablero/DetalleTablero.tsx`: aparatos rótulo + «-K2 · catálogo».
- `neumatica/`: ficha del cilindro, símbolos, accionamiento manual con `estados`.
- `pruebas/VistaPruebas.tsx`: título humanizado.
- `vivo/EventosVivos.tsx` y `panels/KinematicsPanel.tsx`: junta por su hija.
- `vivo/PanelSenales.tsx`: cabecera «rótulo · -K2».
- `visor/FichaPieza.tsx`: una línea «Marcha · -S1» si la pieza es un dispositivo.

**Gates**: los mismos de F3.

### F5 — Revisión de diseño a ciegas · S · ~40 min · depende de F3 y F4

- **Capturas** del muestrario, en el tema vigente (`ui/CLAUDE.md`: hoy sólo oscuro), a ancho
  completo y a `?ancho=420`: Mandos (sesión corriendo, con el seccionador abierto y con la seta
  presionada), Simular falla, Tablero → Aparatos, Neumática y Pruebas.
- **Juez**: un subagente SIN contexto.
- **Rúbrica** (1–5 cada una):
  1. ¿Se entiende qué hace cada control sin conocer la designación?
  2. ¿La designación se encuentra cuando se la busca y no estorba cuando no?
  3. ¿El estado de cada mando que se queda se lee de un vistazo?
  4. ¿Hay texto que sobra o se repite?
  5. ¿La jerarquía es por peso y tamaño, sin cajas ni colores nuevos?
  6. ¿El veredicto dice la verdad y sólo eso?
  7. ¿Algo se ve como deshabilitado sin motivo?
- Lo confirmado se corrige y lo rechazado lleva su porqué en la Bitácora.

### F6 — Verificar con una máquina real · S · ~30 min · depende de F2–F5

- **Por MCP, sobre una API de flota** (nunca la del visor en uso):
  1. un subagente modelador abre una COPIA de la mezcladora;
  2. corre la puerta y comprueba que `interfaz.nombres_por_funcion` sale FALLA con 14 casos y sus
     sugerencias;
  3. declara los rótulos y `estados` con UN `edit_batch`;
  4. comprueba que el ítem queda OK y que `delivery_check` no avisa.
- Mismo cierre en los testigos con tablero.
- **Mario abre «Mandos» y lo juzga**: es el gate final.

**Estimación** (tabla de tiempos medidos):
- agentes: F0 15 + F1 55 + F2 50 + F3 50 + F4 45 + F5 40 + F6 30 ≈ 285 min, más el fix aparte
  (~20);
- merges: tres lotes × ~35 min (F1; F2+F3+F4 juntos en una suite; F5+F6);
- con F2, F3 y F4 en paralelo (tope de 3 agentes): **≈ 4,5–5 h de pared**.

## 7. Lo que este plan NO hace

- No renombra piezas ni cambia geometría.
- No toca el texto del programa del PLC, las hojas de «Señales» ni la lista de conductores: ahí el
  código ES el dato.
- No cambia la BOM ni la cotización (D17).
- No traduce designaciones dentro de textos libres (descripciones de escenarios, ERC para el
  agente).
- No agrega temas ni colores.
- No genera la placa de leyenda en los planos. Queda listo el dato para el plano del tablero, en
  un plan aparte.

## 8. Riesgos

| riesgo | mitigación |
|---|---|
| Toda máquina aprobada con mandos vuelve a FALLA al subir `VERSION_REGISTRO` | Es lo pedido (D18). F6 la cierra en la mezcladora y los testigos; la sugerencia de cada caso hace la corrección un solo `edit_batch` |
| Falsos ✗ o ✓ del criterio | F0 lo mide sobre rótulos reales antes de fijar la tabla; cada ejemplo es un test; la tabla es cerrada y no se abre para aprobar |
| `PanelMandos.tsx` pasa de 500 líneas | F3 parte la fila y el segmentado en componentes |
| La fila de cada ítem de un test con tablero cambia de veredicto | Los fixtures declaran sus rótulos; ningún test se relaja |
| El golden del MCP cambia (brief) | Es deliberado: diff revisado y `--congelar` en F1 |
| El rótulo se escribe en jerga del agente («rs_ok») | Regla 3 de D5; la description del campo lleva ejemplos de placa |
| Dos instancias de `insert_project` con el mismo rótulo | Unicidad por aspecto de función (D5) |

## 9. Bitácora

### F0 — medir (2026-10-27)

Sólo lectura. Verifiqué 26 afirmaciones con archivo:línea: se corrigen 4 (A16).

**Lo medido:**
- **Norma.** El §16.3 sale de la checklist DGUV/IFA 3848 (06.2020) sobre IEC 60204-1:2016; la
  webstore de la IEC confirma la ed. 6.0 + AMD1:2021. El texto de la norma no se leyó.
- **Mezcladora.** 15 operables, y caen los 15. Ningún testigo público tiene carril.
- **Criterio D5 sobre 45 rótulos.** Tal como estaba escrito daba 7 falsos ✓; ajustado da 0.
  Quedan 2 falsos ✗: «Paro de emergencia» y «Marcha/paro».

**Ajustes aprobados.** Prevalecen sobre el texto de las D y F de arriba.

- **A1 — Norma.** La `norma` del ítem es «IEC 60204-1:2016 §16.3 (mandos) · criterio de diseño
  (pilotos y sensores)». Sale el «a confirmar».
- **A2 — Nombre del servicio.** Pasa a `services/nombres_aparatos.py` (con
  `tests/test_nombres_aparatos.py`), porque `services/rotulos.py` ya existe: son los rótulos del
  video.
- **A3 — La `Entrada` vive en `calidad/nombres.py`.** `registro.py` (498 líneas) sólo la importa; su
  docstring se compacta y queda ≤ 500.
- **A4 — Claves de `estados`, por tipo y en UNA tabla pura.**
  - selector: `modelo.posiciones`;
  - electroválvula: las posiciones del carrete, no `lados` (la fila `valvulas` del `inicio` suma
    `posiciones`);
  - seccionador y resguardo: `cerrado`/`abierto`;
  - botonera: sus actuadores.
- **A5 — `estados` nunca suprime un dispositivo.** Es estricto al entrar. Al cargar, una clave
  vencida se ignora con aviso. Se tocan `electrico_eval._dispositivo` y `neumatica_eval.dispositivo`,
  con el test del log que trae una clave vencida.
- **A6 — Literales de `add_device`.** `rotulo`, `estados` y `descripcion` van en sus `literales`:
  una cadena que empieza con «=» es expresión.
- **A7 — Criterio D5 ajustado.** Rechaza también un código de catálogo y una designación dentro del
  rótulo. La tabla cerrada de tipos incluye «pos», fotocélula, final, carrera, seguridad,
  emergencia y los estados sueltos. Los falsos ✗ quedan como casos del test.
- **A8 — Lo que el tipo ya nombra queda fuera del ítem.** La seta, el seccionador, el HMI y la válvula
  de corte, si son ÚNICOS en su aspecto, se muestran con su nombre FUNCIONAL por tipo («Parada de
  emergencia», «Interruptor general», «Panel de operador»). Con 2 o más en el aspecto, entran al
  ítem. La mezcladora queda en 13 casos.
- **A9 — Unicidad por (aspecto, clase).** Mando, indicador y sensor se cuentan por separado: -S1 y
  -P1 pueden llamarse los dos «Marcha».
- **A10 — F6.** Espera la cifra que dé el criterio final, y su `edit_batch` lleva `estados` para -S4,
  -QM1 y -B4.
- **A11 — Se recorre la CADENA SERIE.** Lo que vigila un relé de seguridad y lo que rearma un
  pulsador se leen recorriéndola: desde S12/S22, hacia atrás por los NC, hasta la alimentación. No
  basta la red directa del borne: -K2:S12 sólo ve a -B1. S34 directo vale.
- **A12 — `entrega.semaforo` no repite el ítem.** `semaforo_entrega` descarta la regla «nombres por
  función», porque la juzga su ítem (el precedente es `seguridad.electrico`). `delivery_check`
  sigue avisando, y lo repetido nunca bloquea.
- **A13 — Gates de F2.**
  - El defecto sembrado `mando_sin_rotulo`: un tablero con todos los rótulos menos uno → FALLA.
  - Los 4 testigos se re-congelan con «12» (el ítem va en NO_APLICA) usando
    `scripts/testigos.py --en-proceso --congelar`.
- **A14 — El log viejo.** Su gate es `test_neumatica_carril.py` (`carril_v81_golden.json`), y el
  `circuito` suma `rotulo`/`estados`/`descripcion` SÓLO si están declarados.
- **A15 — La sugerencia limpia antes de cortar.** Quita «·», «(…)» y la designación, y después
  recorta a 30 en palabra. Es texto: nunca aprueba.
- **A16 — Citas corregidas.**
  - `piezas_en_tabla` está en 99-121;
  - `erc` deja pasar los avisos justificados;
  - el aparato de `tablero_panel` está en las líneas 301-302.
- **A17 — Resguardo sin `estados`.** Toma por default «Cerrado/Abierto», y `delivery_check` (no la
  puerta) lo avisa: el RESG-2NC se usa también como sensor de recipiente o de cadena floja.
- **A18 — F3.** El seccionador y el resguardo se leen de `senales` (bool), y el selector y la válvula,
  de `textos`. El `Segmentado` recibe el valor leído; no lo guarda en `useState`.

### F1 — el dato y el respaldo (2026-10-27)

**Hecho.**
- `add_device.rotulo` (≤ 30), `estados` (dict, ≤ 30 por nombre) y `descripcion` (≤ 100), con default
  `""`/`{}`, en `literales` (A6) y en `CAMPOS`. La description del modelo lleva ejemplos de placa, y la
  pista de campo es «Lo que hace, como en su placa…».
- `library/electrico/estados.py` (puro) es la tabla A4: `claves`, `validar` y `filtrar`.
  - Al ENTRAR valida el sello de `add_device` (`al_crear`/`al_editar`). Al editar sólo valida si
    cambian `estados` o la ref, así un estado vencido no traba la edición de otro campo.
  - Al CARGAR, los dos caminos (`dispositivo_desde_ficha`, `neumatica_eval.dispositivo`) filtran: lo
    vencido queda en `Dispositivo.estados_vencidos` y el aparato se conserva (A5). `circuito` lo dice
    en `estados_vencidos` + `aviso_estados`.
- `Dispositivo.rotulo/estados/descripcion/estados_vencidos` en `FUERA_DE_FIRMA`.
- `services/nombres_aparatos.py` (A2) da:
  - `Nombres` con `rotulo_de` (cadena D3 + `origen`; A8 en el paso 4);
  - `estados_de`, `grupo_de` (D11), `vigila` y `rearma_a` (A11, por la cadena serie);
  - `ramas` (el cable por sus extremos) y `fila`;
  - `limpiar_nombre_pieza` (A15), `nombre_junta` (D15) y `humanizar` (D14);
  - `para_tabla` + `nombres_en_tabla` para el vivo.
- Consumidores, todos con claves AGREGADAS:
  - el `inicio` del vivo: `rotulo`, `origen`, `grupo`, `estados`, `descripcion` y `rearma` por fila;
    `posiciones` en `valvulas`, `nombre` en `ramas` y `juntas`, y `titulo_escenario`;
  - Tablero → aparatos: `rotulo`/`origen`; el calentamiento dice «Interruptor general (-Q1)»;
  - Neumática: `nombres` por designación;
  - Pruebas: `titulo` por fila;
  - `circuito`: sólo lo declarado (A14).
- `guidelines.py`: el `corto` («con su rótulo»), el `detalle` (ajustado a A8: la seta, el
  seccionador y el panel de operador únicos no lo necesitan) y el golden del MCP re-congelado (sólo
  cambia la línea 11 de las instructions).

**Decisiones con criterio (vetables).**
- **D7 también en el LOG.** `firma_documento` hashea el log entero, así que ponerle rótulo a una
  máquina probada vencía sus escenarios. `escenarios.PARAMS_FUERA_DE_FIRMA` saca esas tres claves de
  `add_device` antes del hash. Un log sin ellas da el hash de siempre: los 4 testigos de
  `test_firma_dispositivo` no se mueven y no hay `COSIM_EPOCH`, `version` ni `GEOM_CACHE_EPOCH`. La
  firma de la PUERTA (`firma_modelo`) sí las ve, a propósito: el nombre es un ítem suyo (F2).
- **El estricto al entrar va en el sello, no en el evaluador.** En el evaluador, una mutación
  cualquiera revertiría el documento entero por un estado vencido de OTRO aparato.
- **Texto que no se cambió.** Las frases de los ítems de Neumática siguen con la designación (F4 las
  muestra con `nombres`), y el `verificar` de `guidelines` NO dice «avisa los aparatos sin rótulo»:
  sería falso hasta que entre la regla de F2, que lo suma.
- **El respaldo por tipo** se llama «Interruptor de resguardo» (una sola forma, D13). `ambar` del
  catálogo se lee «ámbar». La cadena del relé une los rótulos en minúscula: «Seguridad de parada
  de emergencia y tapa del tanque».
- **Lo que no es de un aparato.** Una rama sin conductor conocido se llama «Cable», nunca su id; una
  junta sin pieza hija, su nombre humanizado sin el prefijo `cNN_`.

**Cifras (F1).** `test_nombres_aparatos.py` tiene 28 casos. Suite completa (`-n auto`): un solo rojo,
`test_pruebas_panel` (comparaba la fila entera y faltaba `titulo`). Se corrigió y se re-corrió
verde junto con los gates de documentos; ruff limpio. El golden v81 (`test_neumatica_carril`) quedó
byte-idéntico y las cuatro firmas de `test_firma_dispositivo` no se movieron.

### F3 — «Mandos» por función (2026-10-27)

**Hecho** (sólo `ui/src/vivo/`, el muestrario y su gate de tokens).
- `protocolo.ts`: `NombreAparato` (`rotulo`, `origen`, `grupo`, `estados`, `descripcion`, `rearma`) en
  mandos, pilotos y dispositivos; `rotulo` en `fallas`, `nombre` en `ramas`, `titulo_escenario`.
- `nombresMandos.ts` (puro): nombre principal y designación secundaria, grupos (D11), segmentos y el
  segmento LEÍDO (A18: `<des>.cerrado` en `lecturas`, `<des>.posicion` en `textos`), el estado junto
  al botón (D10) y el veredicto (D12).
- `FilaMando.tsx` (la fila, `CabezaAparato` con la ⓘ de D16, pilotos) y `Segmentado.tsx` (recibe el
  valor; sin `useState`). `PanelMandos.tsx` queda en 214 líneas.
- `mandos.css`, sólo tokens, entra a `diseno/tokens.test.ts`.
- Se borraron `NOMBRES`/`nombreTipo`/`nombreConEstado` de `mandos.ts`, `TIPOS`/`nombreTipoFalla` de
  `fallas.ts` y los rótulos por tipo de `lecturas.ts`. Sin rótulo (servidor anterior) se muestra la
  designación sola.
- «Simular falla»: «Seguridad de tapa y seta · -K2», el contacto y el cable con el `nombre` del
  servidor. Las activas, «contacto 13-14 pegado cerrado en Seguridad de tapa y seta».
- La apertura lista el `titulo` humanizado: `api.escenarios` lee `/api/pruebas` (trae `titulo`
  desde F1); `/api/escenarios` no se tocó, porque cambiarlo movía el golden del MCP.
- Muestrario: «Mandos · mezcladora de paletas» con 8 mandos, 4 pilotos, 2 relés y las fallas con
  rótulos. `?mandos=rearmar|marcha|sin-energia|seta|tapa` fija el estado inicial.

**Decisiones con criterio (vetables).**
- **`--fs-chico` no existe**: la designación va en `--fs-nota` (11 px), el más chico del tema. No
  se crea un token para lo mismo.
- **Veredicto**: el primer hecho que bloquea es la frase y los demás van en la nota. Si cortan
  TODOS los relés, «La seguridad corta la marcha»; si corta uno, va por su nombre. El resguardo se
  dice con SU estado declarado («Tapa del tanque abierta»); un estado de varias palabras va tras
  dos puntos («Recipiente bajo la descarga: sin recipiente»). La severidad es `aviso` y, sin nada
  que bloquee, `bien`.
- **El segmento marcado sale sólo de la señal** (`lecturas`/`textos`), sin las `esperadas`: si el
  servidor rechaza, no se ve nada que no pasó. La tapa y el botón siguen con `valorVisto`.
- **Seccionador o resguardo sin `estados`** (servidor anterior): el botón con verbo de siempre, no
  un segmentado con las claves crudas.
- **La seta** dice «Liberada/Presionada» junto a su botón (el estado de un botón, no un nombre de
  tipo). El rearme, «Falta rearmar/Rearmada» sólo si todos sus relés publicaron `salidas`.
- **El estado y el control van en un bloque**: en angosto bajan juntos, nunca el botón solo.
- **Fuera de F3** (F4 o una fase propia): `arbolSenales.ts` conserva su `TIPOS` (lo usa
  `PanelSenales`, de F4) y `neumatica/AccionamientoManual.tsx` sigue con `.fila-mando-nombre`. Sólo
  se tocó una línea de `neumatica/neumatica.test.ts` (el cilindro sin rótulo ya no se llama «Cilindro»):
  ojo al mergear con F4.

**Cifras.** `npm test`: 76 archivos y 619 tests, verde, con `nombresMandos.test.ts` nuevo (13).
`npm run build` verde. Visto en el muestrario a 420 px y en el ancho de columna: rearmar, abrir el
seccionador y abrir la tapa cambian el veredicto, el segmento y el estado.

### F4 — el resto de las superficies (2026-10-27)

**Hecho** (sólo `ui/`; sin Python).
- **Una pieza para todas**: `diseno/NombreAparato.tsx` (rótulo en `--fw-medio`; detrás, en
  `--fs-nota` y tinta secundaria, la designación que nunca se corta y un detalle opcional) y lo puro
  en `diseno/nombres.ts` (`nombrePrincipal`, `designacionSecundaria`, `nombreEnLinea`,
  `nombreDeJunta`). Su CSS pasó de `vivo/mandos.css` a `diseno/diseno.css`; `nombresMandos.ts` y
  `CabezaAparato` de F3 la reusan.
- **Tablero → Aparatos**: «Seguridad del recipiente» y debajo «-K3 · Relé de seguridad 2 canales…»
  (`AparatosTablero`, exportada para el muestrario). En la lista, la parte secundaria va SIEMPRE en
  su línea: las filas miden igual. «Admite Interruptor general (-Q1)» en el calentamiento, con el
  rótulo de la misma lista. `datosTablero.ts`: la piloto con sus rótulos por tipo y el texto de
  calentamiento como lo escribe hoy el servidor.
- **Neumática**: la ficha del cilindro («Cilindro de compuerta · -MM1 · Ø32 mm…»), lo elegido en el
  esquema con `nombres` («Caudal de apertura · -RZ1 · Regulador de caudal»: los dos reguladores ya no
  se leen igual) y el `aria-label` de cada símbolo. El accionamiento manual es la fila de «Mandos»:
  la válvula por su rótulo y al lado la posición por su nombre («Compuerta cerrada»); sin nombre
  declarado, «Reposo (12)», nunca «posición 14». `ValvulaVivo` suma `NombreAparato` y `posiciones`.
- **Pruebas**: el título es `titulo`; el id va en «Detalle técnico» de la prueba abierta.
- **Eventos**: cada junta por su `nombre`; el id sólo si dos se llamarían igual.
- **Cinemática**: la junta por el nombre de su pieza hija (de la escena), el id detrás y chico, y
  «giratoria (°) · sobre <padre>».
- **Señales**: cabecera «rótulo · -K2» con el `rotulo` de `dispositivos`; un cable, por el `nombre` de
  su rama («Cable Red de suministro → Interruptor general · -W1»). Se borró `TIPOS` de
  `arbolSenales.ts` (D13); el buscador encuentra por rótulo y por designación.
- **Ficha de pieza**: una línea «Marcha · -S1» si la pieza es un aparato, con lo que la UI ya leyó
  (`visor/aparatoDePieza.ts`: el `inicio` del vivo, «Tablero», «Neumática»). Sin endpoint nuevo.
- **Muestrario**, todo de la mezcladora: «Tablero · aparatos de la mezcladora» (17), «Neumática ·
  compuerta» (`neumaticaMezcladora.json`, la salida REAL de `neumatica_panel.panel` sobre un circuito
  como el suyo, generada offline), «Pruebas» con 6 escenarios humanizados, «Señales» y, dentro de
  «Mandos», «Provocar atasco» y el accionamiento manual. `INICIO_DEMO.dispositivos` lleva ahora todos
  los aparatos, como el servidor.

**Decisiones con criterio (vetables).**
- **Cinemática sin clave nueva en `/api/kinematics`**: el nombre de la pieza hija sale de la escena
  (dato del servidor), entero, sin la limpieza A15 de `nombre_junta`. Sumar `nombre` al endpoint era
  tocar Python y la suite por una cifra de texto; si la puerta del layout se lee larga, F5 lo dice.
- **Ficha de pieza sólo con lo ya leído**: sin sesión viva ni «Tablero»/«Neumática» abiertos no hay
  línea. Una fuente general pediría una clave por pieza en la escena (`aparato: {designacion,
  rotulo}`): no se creó; queda para una fase si F5 o Mario la piden.
- **Eventos**: un `<select>` no tiene «secundario»; el id va sólo al desempatar (`ui/CLAUDE.md`: los
  ids, a pedido).
- **Lo que NO cambió y es del servidor**: las frases de los ítems de Neumática siguen con la
  designación («Falta el límite elástico del vástago de -MM1») y el calentamiento dice «El más justo
  es Interruptor general (-Q1)» (mayúscula a media frase). La UI no reescribe frases del servidor:
  el arreglo es `neumatica_panel` con `Nombres.con_designacion` (como `tablero_atencion`) y una
  minúscula en `con_designacion` para usarla dentro de una frase. Al backlog de F2 o una fase S.

**Cifras.** `npm test`: 77 archivos y 633 tests, verde, con `diseno/nombres.test.ts` nuevo (7: rótulo
primero, designación secundaria, la junta, la ficha y «sin tabla de tipos» sobre el código de cada
superficie) y casos nuevos en `neumatica`, `senales`, `tablero/vista` y `pruebas`. `npm run build`
verde. Visto en el muestrario al ancho de columna y a 420 px.

### F2 — la regla que obliga: puerta y entrega (2026-10-27)

**Hecho.**
- `library/calidad/nombres.py` (puro): el criterio D5 + A7 con la tabla CERRADA de la F0 § 3.2
  (`motivo_rotulo`, `motivo_estado`), el alcance con A8 (`en_alcance`: la seta, el seccionador, el
  HMI y la válvula de corte únicos en su (aspecto, tipo) quedan fuera), la unicidad por (aspecto,
  clase) de A9, los estados del selector y de la electroválvula manual, los casos (designación,
  motivo, piezas, `sugerencia`) y la `ENTRADA` de `interfaz.nombres_por_funcion` (A3, norma de A1,
  familia «seguridad»). FALLA sin justificación; SIN_EVALUAR si el insumo es `{"error"}` o el
  control lanza; NO_APLICA sin operables.
- `registro.py`: importa y lista la entrada, `VERSION_REGISTRO = "12"`, docstring compactado (457
  líneas).
- `services/nombres_aparatos.insumo_puerta`: una fila por aparato con lo DECLARADO, las claves de sus
  estados, su pieza 3D (`tablero.piezas_3d`) y la sugerencia (`de_pieza`, A15). Se lee UNA vez en
  `delivery_inputs` (kwarg `nombres`, sólo con carril) y de ahí la toman la regla de la entrega, el
  detector `elementos["operables"]` (`puerta_hechos`) y el insumo `nombres` de `reunir`.
- `delivery.py`: la regla «nombres por función» (AVISO) en tres filas: mandos/pilotos/sensores, lo
  repetido (D2) y el resguardo sin `estados` (A17). `VERSION_BATERIA` 3 → 4. `semaforo_entrega`
  descarta las reglas con ese prefijo y las cuenta en `con_item_propio` (A12).
- `set_scenario` (`escenarios.poner`): aviso si la `descripcion` trae un id de comando o de pieza
  (`avisos_descripcion`, D14).
- `guidelines.py`: el `verificar` de `electrico` dice que `delivery_check` avisa y que la puerta
  exige el rótulo. El golden del MCP no cambió (el `verificar` no está en las instructions).
- Gates: `tests/test_puerta_nombres.py` (los 45 rótulos de la F0, con los 2 falsos ✗ anotados);
  el defecto sembrado `mando_sin_rotulo` (ménsula + arranque directo sin el rótulo de -S2); los 4
  testigos re-congelados: sólo cambian `version_registro` y el ítem nuevo en NO_APLICA.

**Decisiones con criterio (vetables).**
- **`calidad/entrada.py`.** `Entrada` y los predicados (`siempre`, `hecho`, `hay`, `hay_alguno`)
  salen de `registro.py`, que los re-exporta por identidad: si `nombres.py` importara `registro.py`
  habría un ciclo (registro importa nombres para listar su `ENTRADA`).
- **`REPETIBLES` (D2) es una tabla cerrada**: relés, relés de seguridad, contactores, variadores,
  motores, cilindros, electroválvulas sin mando manual, válvulas, reguladores de caudal,
  silenciadores y bloqueos de vástago. Las protecciones (ITM, guardamotor, térmico, fusible,
  diferencial) se nombran por lo que protegen; la red, la fuente, el PLC y el FRL, por su tipo.
- **La válvula de corte** entra al alcance como mando sólo si hay dos en un aspecto (A8). Sola, queda
  fuera, como en la F0.
- **La sugerencia es sólo el nombre de la pieza** (A15). La variable del PLC conectada (D3) no se
  sugiere: pide recorrer el ST y queda para F6 si hace falta.
- **Una sola lectura del carril por corrida.** El insumo viaja en los kwargs de la entrega, como
  el acceso de herramienta: así el detector y el control no pueden discrepar.

**Cifras.** La mezcladora (`-agujeros.apolo`, leída como ZIP sin tocarla) da **13 casos** en el ítem:
-S1…-S4, -P1…-P4, -B1…-B4 y -QM1. -S4 y -QM1 además piden sus `estados`. La entrega suma 7 repetidos
(-K2/-K3 y -RZ1…-RZ5) y los 2 resguardos sin estados (-B1, -B4). 5 de los 13 traen sugerencia de
pieza.

Suite completa (`-n auto`): un solo rojo, `test_electrico_servicios::test_con_carril_el_erc_entra_al_semaforo`
(esperaba VERDE con el arranque directo sin rótulos). No se relajó: ahora comprueba el aviso y el
fixture declara sus rótulos (`tablero_electrico.con_rotulos`) para dar VERDE. Re-corrida verde;
ruff limpio.

### F6 — la mezcladora real, por MCP (2026-10-27)

Un `claude -p` con sólo las tools `apolo-cad` corrió sobre una API de flota (copia de la
mezcladora, base propia): 2 min, 14 turnos, 0,97 USD.
- Antes: `interfaz.nombres_por_funcion` FALLA con 13 casos (lo que daban A8 y F2).
- UN `edit_batch` sobre 20 `add_device`: los 13 del ítem, más -K2/-K3 y -RZ1…-RZ5. Las claves de
  `estados` («0»/«I» del selector, «14»/«12» de la válvula) entraron a la primera.
- Después: el ítem queda OK y la puerta APROBADA (v12: 29 OK, 0 FALLA, 0 SIN_EVALUAR).
  «Nombres por función» sale OK en `delivery_check` (AMARILLO por otros 3 avisos que ya
  estaban).

**Lo que encontró:**
- Por MCP, el detalle nombraba 4 aparatos «y 9 más», sin sugerencia. **Corregido**:
  `tools/calidad.resumir` trae los `casos` por aparato (hasta 20, con motivo y sugerencia).
- El nombre de -RZ1/-RZ2 (caudal de apertura o de cierre) sale distinto en el muestrario y en el
  modelador. Queda a verificar contra el sentido del aire en el esquema.
- `scripts/flota.py parar` dio un falso «QUEDA ALGO»: contó procesos del sistema (pid reciclado,
  `suyo` en True sin hora de creación). Pasa al backlog.
- Los `estados` de una electroválvula salieron como verbos («Abre la compuerta») y el visor
  muestra estados («Compuerta cerrada»). Los dos se leen bien; la description de `add_device`
  da verbos de ejemplo.

Falta el gate final: Mario abre «Mandos» con la mezcladora con nombres
(`C:\t\f6\mezcladora-con-nombres.apolo`).

### F5 — revisión a ciegas (2026-10-27)

**El juez** (subagente sin contexto, capturas del muestrario a ancho de columna y a 420 px) puso, de 1
a 5: **1: 4 · 2: 4 · 3: 3 · 4: 3 · 5: 3 · 6: 3 · 7: 3 · 8: 3**. Lo confirmado se corrigió en F5b, en
una fase (UI + tres frases del servidor).

**Corregido (F5b).**
1. **Pruebas.** Mientras corre (o espera), la fila dice «Corriendo» / «En espera» con el semáforo neutro,
   nunca el «Pasa»/«Falla» viejo (`vista.estadoDeFila`). «Todavía no se corrió» se quitó: el estado ya
   dice «Sin correr». La vencida dice debajo «Hay que volver a correrla» (`lineaBajo`). «Lo que no
   cumplió» lleva arriba una frase llana del SERVIDOR (`services/pruebas_frases.py`: «La carrera del
   cilindro de compuerta (-MM1) tenía que estar siempre por debajo de 5 mm» y «A los 3,4 s estaba en
   12 mm», claves AGREGADAS `frase` y `paso` en cada fallida); la expresión y su cifra crudas, en
   «Detalle técnico» junto al id del escenario.
2. **Veredicto de Mandos (D12).** El título es la causa leída («Sin energía», «Parada de emergencia
   presionada», «Tapa del tanque abierta», «Seguridad sin rearmar») y la nota, la acción de los mismos
   hechos («Enciende el interruptor general», «Libera la parada de emergencia», «Cierra la tapa del
   tanque», «Rearma la seguridad»). Un relé ya no se nombra con un verbo pegado.
3. **El próximo paso, destacado.** El veredicto trae `paso` (el mando y, si se queda, el segmento): ese
   botón o segmento toma el `button.primary` del tema; ningún otro. Nada se deshabilita (D10).
4. **Lo que se queda.** El segmento elegido gana fondo `--panel3`, anillo `--accent` y peso; los otros, en
   `--text` (antes `--muted`: parecían apagados). El cuadrado del color físico sólo en pulsador y seta
   (`muestraColorFisico`); los pilotos siguen con su lámpara.
5. **Filas.** La fila de un mando no salta: el nombre arranca en ancho 0, crece y se parte en dos líneas
   (nunca más angosto que su palabra más larga); si el estado y el control no entran lado a lado, el
   estado baja DEBAJO del control, que se queda en la línea del nombre.
6. **Lecturas y Señales.** Las lecturas son una grilla nombre (≥ la mitad) | valor a la derecha, que baja
   por partes enteras («Carrera 200 mm» / «avance 6,0 bar»). La designación es texto corrido pegado a la
   última palabra (`::before` con espacio duro; la ⓘ, pegada a ella): nunca huérfana. En «Señales» se
   **quitó** la cuenta de la derecha: en ese panel la derecha es el VALOR y un número suelto se leía como
   una lectura; las señales se ven al abrir la fila.
7. **Frases del servidor.** `nombres_aparatos.en_frase` (artículo por la primera palabra, sigla
   masculina) y `Nombres.con_designacion(frase=True, prep=…)`, la variante del helper de F1: «Falta el
   límite elástico del vástago del cilindro de compuerta (-MM1)» (todas las frases de
   `neumatica_panel`), «El más justo es el interruptor general (-Q1)», y la barra de fallas, «contacto
   soldado en el contactor -KM1» con la clave AGREGADA `en_frase` de cada fila del `inicio`.
8. **Neumática.** El tiempo de carrera con centésimas («0,16 s»). `cifra()` y `lecturas.formatear` unen
   número y unidad con espacio duro (como `neumatica_panel.n` en el servidor) y «carrera 200 mm», «Fuerza
   a 6 bar» no se parten. El esquema agranda su vista para los textos agrandados a la letra mínima
   (`vistaConTextos`): «-RZ2» perdía su «2» en el borde.

**Decisiones con criterio (vetables).**
- **El género lo decide el servidor** (`en_frase`), no la UI: «el nombre lo da el servidor» (D13). La
  regla es de terminación con dos listas cortas de excepciones (`fuente`, `red`… / `sistema`,
  `programa`…); un rótulo que la engañe se lee raro, nunca miente. Sin `en_frase` (servidor anterior), la
  UI pone el rótulo en minúscula sin artículo.
- **Un resguardo cuyo estado cerrado no es «Cerrado»** («Acoplado») pide «Pon el recipiente bajo la
  descarga en «Acoplado»»: el verbo no se deriva de un participio cualquiera.
- **La nota dice UNA acción**, la del primer bloqueo: los demás aparecen al resolverlo. Antes la nota
  listaba los otros bloqueos.
- **La parte de un aparato de varias piezas no es su nombre**: el respaldo «pieza» (D3.2) de un cilindro
  ligado a «Cilindro · Cuerpo» daba «El cuerpo (-MM1)…»; si el comando de la pieza creó varias, se usa
  el tramo de antes («Cilindro»).
- **Lo que no se dice en llano** (booleanas, variables del PLC, el balance de producto, una señal de una
  pieza) queda con su expresión: una frase inventada sería peor que la cruda.
- **La barra de fallas sin paréntesis** («el contactor -KM1»), como pidió la revisión; las frases del
  servidor van con paréntesis («el interruptor general (-Q1)»). El cable de campo sigue «en Red de
  suministro → Interruptor general»: su nombre es una ruta del servidor, no un aparato.

**Rechazado, con su porqué.**
- **Quitar las cajas de las filas**: es el patrón de lista agrupada del tema, el mismo de todos los
  paneles; quitarlo en «Mandos» rompería la consistencia, no la jerarquía.
- **Renombrar «Par» en Eventos**: es la magnitud correcta, con su unidad (N·m) al lado.

**Para F6.** Mario juzga «Mandos» con la mezcladora real: los rótulos declarados por `edit_batch` y que
`en_frase` lea bien sus géneros.

### Cierre (2026-10-27)

Mario abrió «Mandos» de la mezcladora con nombres en el visor y lo dio por bueno («mucho mejor»). Hubo una traba al mostrarlo: el visor con `-Pro` sirve la UI COMPUESTA de la extensión, compilada aparte, y siguió mostrando la vieja hasta recompilarla.
