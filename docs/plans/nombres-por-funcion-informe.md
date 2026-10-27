# Nombres por función en el visor — informe

Anexo del plan [nombres-por-funcion](nombres-por-funcion.md): el inventario medido, la fuente del nombre, las maquetas y las líneas de las reglas.

Pedido de Mario (2026-10-27), sobre el panel «Mandos» de la mezcladora en la sesión viva: «tienes
que darle un nombre y descripción para saber lo que hace … no te digo que lo rellenes de texto, sé
más como Apple, pero no entiendo cuando dice solamente -Q1, tendría que ver los planos para eso».

Leído en `main` (`d3b2db6`) y en la API de solo lectura `127.0.0.1:8197` (proyecto 1, «Mezcladora
de paletas 200 L», 393 comandos, 33 dispositivos). Marcas: **[dato]** = medido en el código o en
la API, con `archivo:línea`; **[opinión]** = criterio mío, vetable.

---

## 1. Inventario por superficie, de más grave a menos

La vara: qué entiende alguien que abre el visor por primera vez y quiere mirar y probar, sin los
planos al lado.

### 1.1 «Mandos» de la sesión viva — GRAVE (es donde se ACTÚA)

[dato] Cada fila pone la designación en negrita como lo principal y, al lado, sólo el TIPO genérico:
- `ui/src/vivo/PanelMandos.tsx:168`: `<strong>{m.designacion}</strong>`.
- `PanelMandos.tsx:169`: `nombreConEstado(m, estado)` + «también con clic en el 3D».
- `ui/src/vivo/mandos.ts:64-85`: el nombre es una tabla por tipo («Pulsador», «Selector»,
  «Seccionador», «Resguardo»).

Resultado: -S1, -S2 y -S3 se leen IGUAL («Pulsador [Presionar]»). Sólo el color de la tapa los
distingue, y el color no dice que el azul es el rearme.

[dato] El servidor tampoco tiene el dato:
- `cosim/vivo_fotograma.py:62-76` arma cada mando con `designacion, tipo, ref, color, pieza…`, sin
  ningún nombre;
- `vivo_fotograma.py:112`: el piloto, igual;
- `AddDeviceParams` (`commands/models_electrico.py:70-136`) no tiene campo para el nombre;
- `Dispositivo` (`library/electrico/modelo.py:75-111`) tampoco.

Defectos que agravan, todos [dato]:
- **El selector no muestra en qué posición está.** `PanelMandos.tsx:245` guarda la posición en un
  `useState(null)` local. Al entrar no hay ninguna marcada, aunque el modelo la publica
  (`cosim/modelos/mandos.py:198-199`, señal `<des>.posicion`). Viola la regla de `ui/CLAUDE.md`
  «un estado de la máquina se LEE de su señal». Además «-S4 [0][I]» no dice que 0 = manual y
  I = ciclo; eso sólo está en un comentario del ST: «(* -S4 selector: I = CICLO, 0 = LOCAL *)».
- **«también con clic en el 3D» se repite en cada fila con pieza.** En la mezcladora son las 8
  filas, porque el layout del tablero liga todas (`services/tablero.py:99-121`). Son ~40 palabras
  de la misma frase: el presupuesto entero del panel (`ui/CLAUDE.md` § Texto, ~40 palabras).
- **-B1 y -B4 dicen «Resguardo cerrado [Abrir]».** -B4 no es un resguardo para quien mira: es «hay
  un recipiente acoplado bajo la descarga». «Abrir» un recipiente no significa nada.
- **«Pilotos»: cada fila dice «-Pn · Piloto · Apagado»** (`PanelMandos.tsx:276-280`). -P3 y -P4
  son los dos ámbar: indistinguibles.
- **«Lecturas»: -K2 y -K3 salen las dos como «Relé de seguridad · Habilita la marcha»**
  (`ui/src/vivo/lecturas.ts:76`). Una vigila tapa y seta; la otra, el recipiente.
- **Una cosa, dos nombres.** El mismo aparato es «Resguardo» en Mandos (`mandos.ts:69`) e
  «Interruptor de resguardo» en «Simular falla» (`ui/src/vivo/fallas.ts:50`). Hay TRES tablas de
  nombres de tipo en la UI: `mandos.ts:64`, `fallas.ts:45` y `arbolSenales.ts:18`, más los
  rótulos sueltos de `lecturas.ts:63-85`.
- **La apertura lista el id del escenario** («ciclo_nominal», `PanelMandos.tsx:90`).

[dato] El nombre con sentido YA existía, pero sólo para algunos aparatos:

| aparato | dónde está el nombre | ¿alcanza? |
|---|---|---|
| -B1 | pieza `c66` «Interruptor de tapa -B1» | sí |
| -B4 | pieza `c361` «Interruptor de recipiente acoplado -B4» | sí |
| -B2, -B3, -QM1, -RZ1… | su pieza de campo | sí |
| -S0…-S4, -P1…-P4, -Q1 (todo lo de la PUERTA) | pieza generada por `layout_tablero`: «Tablero de control +TAB1 · -S1 Pulsador Ø22 verde 1NA» (`commands/tablero.py:156-157,194`: el nombre de catálogo) | **no** |
| -S1, -S2, -S4, -P1…-P4 | comentarios del ST | a medias |
| -S0, -S3, -Q1 | — (el rearme y la seta van cableados a -K2/-K3, no al PLC: `-S3:14 → -K2:S34` y `-K3:S34`) | **no** |

Los mandos que más importan para probar la seguridad son justo los que no tienen nombre en
ningún lado.

### 1.2 «Simular falla» (dentro de Mandos) — GRAVE

[dato] `FallasVivas.tsx:100`: la opción es `designacion · tipo` y, para una rama, su `id` crudo:
- un contacto sale como «-K2:13-14 · Contacto»;
- un conductor sin cable sale con el id del COMANDO, p. ej. «c160 · Cable»
  (`services/cosim_red.py:231`: `base = … cond.id`).

[opinión] Para provocar una falla con sentido («que se pegue el contacto que corta el motor») hay
que saber qué es cada código: hoy hace falta el plano.

### 1.3 «Neumática» y «Accionamiento manual» — ALTA

[dato]
- `AccionamientoManual.tsx:42-54`: «-QM1 · Sin accionar · posición 14 [Accionar a mano · 14]».
  El «14» es el puerto ISO de la bobina, no lo que pasa: abrir la compuerta.
- `VistaNeumatica.tsx:82`: el cilindro es «-MM1 · Ø32, vástago 12…», aunque su pieza se llama
  «Cilindro de compuerta».
- El esquema (`GET /api/neumatica` → `esquema.simbolos[].rotulo`) da «Regulador de caudal» dos
  veces (-RZ1, -RZ2) y «Silenciador» tres veces. Las piezas dicen «(puerto B)», «(puerto A)»,
  «escape corte».
- Los ítems hablan en designaciones: «El vástago de -MM1 pandea…» (`services/neumatica_panel.py:137`).

**Hallazgo aparte, MIENTE** [dato]: esa frase dice «pandea» SIEMPRE que la regla no es «ok». En la
mezcladora el estado es «aviso» porque λ < 100 sin `fy` declarado (`library/neumatica/calculo.py:244-246`),
con FS = 109. El panel afirma que el vástago pandea cuando no pandea. Según `ui/CLAUDE.md`
§ Limpiar («primero lo que miente») va antes que todo lo demás. Es un fix aparte y chico.

### 1.4 «Tablero» — MEDIA

[dato]
- «Aparatos» (`DetalleTablero.tsx:57`, datos de `services/tablero_panel.py:301`): «-K2 · Relé de
  seguridad 2 canales 24 VDC» y «-K3 · Relé de seguridad 2 canales 24 VDC»; «-P3 · Piloto LED Ø22
  ámbar» y «-P4 · Piloto LED Ø22 ámbar». La designación manda; el secundario es el CATÁLOGO, no el
  rol.
- «Calentamiento» dice «El más justo es -Q1: 46 de 50 °C».
- Los conductores son «-G1:L1 → -Q1:1» (`DetalleTablero.tsx:168-179`).

[opinión] Los conductores están bien así: es la vista del que cablea y el borne ES el dato. Basta
el rótulo del aparato al elegir la fila.

### 1.5 «Pruebas» — MEDIA

[dato]
- `VistaPruebas.tsx:65`: el título de la fila es el id `nombre` («descargar_sin_recipiente»).
- `VistaPruebas.tsx:102`: muestra la `descripcion` que escribió el modelador. Trae jerga de
  agente: «SF3: sin recipiente acoplado (-B4 abierto) … salida Q0.2 del PLC pegada a 1 (la bobina
  de -QM1 pasa por -K3 13-14). Arranca con la compuerta CERRADA (c68_vastago inicial 200 mm)».
- Las 7 descripciones terminan en «(c68_vastago inicial 200 mm)», un id de pieza.

### 1.6 Eventos, Cinemática y Señales — MEDIA-BAJA

[dato]
- «Provocar atasco» elige la junta por su `name` (`EventosVivos.tsx:23`).
- Cinemática muestra `j.name` en negrita (`KinematicsPanel.tsx:194`): «j_eje_paletas»,
  «j_tapa_carga» y la del layout, «c388_puerta», que es un id.
- El árbol de «Señales» titula con la designación y el tipo
  (`arbolSenales.ts:52`: «-K2 · Relé de seguridad»).

[opinión] Las HOJAS de Señales («salidas», «espera_ciclo») y el texto del panel PLC se quedan como
están: son los nombres que el agente usa en las aserciones y en el programa. Ese es el dato del
instrumento.

### 1.7 Árbol, ficha de pieza y Propiedades — BAJA

[dato] `FichaPieza.tsx:60-61` muestra nombre + id. Un aparato de la puerta se llama «Tablero de
control +TAB1 · -S1 Pulsador Ø22 verde 1NA» y nada dice «Marcha».

El id a la vista en el árbol es una excepción deliberada de `ui/CLAUDE.md`, y se respeta.

### 1.8 BOM y cotización — BAJA (y no necesita rótulo)

[dato] `BomPanel.tsx:78`: la primera columna es `Ref` en `<code>`, con pseudo-refs «A-MEDIDA» y
«COMPRA» en la mayoría de las 127 filas. «RESG-2NC ×2» no dice que son -B1 y -B4.

[opinión]
- La BOM es para COMPRAR: la ref es dato legítimo y el rol no hace falta.
- Lo que ayuda es poner Descripción primero y una columna de designaciones («-B1, -B4») para cruzar
  con el plano.
- Va a backlog, no a este plan.

### 1.9 Puerta de entrega / publicación

[dato] El visor del núcleo no tiene superficie para ella (sólo MCP y extensiones). Sus textos
(`erc.py:62`, `_quien` = «-K2 (RS-2C-24VDC)») son del agente: quedan como están.

### 1.10 Etiquetas 3D de la sesión viva

[dato] `vivo/etiquetas.ts:53` pone la designación sobre la pieza («-M1 1450 rpm»).

[opinión] Ahí basta: la pieza misma dice qué es. Ver § 3.6.

---

## 2. De dónde sale el nombre

### 2.1 Recomendación: un DATO declarado en `add_device`, con respaldo derivado y marcado

Tres campos nuevos y opcionales de `AddDeviceParams`:

| campo | qué es | tope | ejemplo |
|---|---|---|---|
| `rotulo` | lo que el aparato HACE para quien opera: el texto de su placa de leyenda | ≤ 30 caracteres | «Marcha», «Rearme de seguridad», «Tapa del tanque» |
| `estados` | el nombre de cada posición o estado de SU ficha | — | selector `{"0": "Manual", "I": "Ciclo"}`; resguardo `{"cerrado": "Acoplado", "abierto": "Sin recipiente"}`; electroválvula `{"14": "Abre la compuerta", "12": "Cierra la compuerta"}` |
| `descripcion` | sólo cuando rótulo + verbo no lo dicen todo; va a la ⓘ, nunca a la vista | ≤ 100 caracteres, una frase | -S2: «Además borra la falla de la compuerta» |

Por qué un dato y no una derivación [dato]:
1. **Los mandos de la puerta no tienen otra fuente.** Su pieza la nombra `layout_tablero` con el
   CATÁLOGO, y -S0/-S3/-Q1 ni pasan por el PLC.
2. **Los comentarios del ST son texto libre.** Leerlos asignaría mal:
   - «(* canal 1 tras -S0 y -B1 (diagnostico) *)» nombra a dos aparatos y no es el rol de ninguno;
   - «(* -K2 33-34: rele de seguridad de tapa/seta habilitado *)» le daría a -K2 el rótulo
     «33-34: rele…».
3. **Las variables del PLC son jerga** («rs_ok», «recip_no_acop», «paro_ok»).
4. **Es un ENTREGABLE.** IEC 60204-1 pide marcar cada mando e indicador con su función, en él o
   junto a él (§ 16.3 «identificación funcional»; edición y numeral a confirmar contra el texto en
   la F0, regla de citas). La placa de leyenda del tablero y el texto de función del esquema son
   ese mismo dato. Cumple la doctrina de resultados: mejora un plano, no sólo la pantalla.

**Por qué en el comando y no en el manifest** [opinión fundada]: la designación, la ubicación y el
`name` de toda pieza ya viven en el log. Además:
- `insert_project` copia el carril con su prefijo (`commands/electrico.py:131-160`), así que el
  rótulo viaja solo;
- el undo sale gratis;
- un metadato aparte necesitaría su propia copia en cada inserción.

Descartado meterlo en `ajustes`: se valida contra el `modelo` y ENTRA a la firma de los escenarios.

### 2.2 Compatibilidad (verificado contra las reglas del repo)

- **Log viejo**: los campos nuevos nacen con default `""`/`{}`, así que regenera igual. No hace
  falta upcaster. El trinquete D12 (`tests/test_contrato_comandos.py`) pide anotar los campos en
  `CAMPOS`.
- **Params estrictos**: son campos DECLARADOS, así que la entrada los acepta y el replay ignora
  cualquier otro. `estados` se valida contra la ficha en el EVALUADOR, como `ajustes` (depende de
  la ref).
- **`version` del executor / `GEOM_CACHE_EPOCH`**: nada.
  - `add_device` es del carril (`_exec_carril`, `commands/electrico.py:40-49`) y su huella no cambia.
  - `layout_tablero` sólo lee `ref, designacion, ubicacion, cantidad, pieza`
    (`doc/carril.py:101-104`). Si el rótulo NO entra a `CAMPOS_LECTURA`, cambiarlo no re-ejecuta
    el layout ni los 40 comandos que tiene detrás.
  - Por eso el nombre de la pieza del tablero NO cambia; el rótulo se une al LEER (D6 del plan).
- **Firma de escenarios**: `Dispositivo.rotulo/estados/descripcion` van a
  `services/escenarios.FUERA_DE_FIRMA` (`:49`); no son física. Renombrar no vence ningún resultado.
  El test `test_firma_dispositivo.py:129-136` obliga a decidirlo.
- **`COSIM_EPOCH`**: nada. El worker no los ve. Se suman al `inicio` en la API, como ya hace
  `piezas_en_tabla` (`services/tablero.py:99`, llamada en `api/routers/cosim_vivo.py:286`).
- **Contrato del `inicio`** (`test_fotograma_contrato.py`): AGREGAR claves no sube `version`.
- **`VERSION_BATERIA`** (`library/delivery.py:27`): sube, porque entra un chequeo nuevo a
  `delivery_check` (§ 2.3).
- **`VERSION_REGISTRO`** (`library/calidad/registro.py:82`): "11" → "12", por el ítem nuevo
  (§ 2.5).

### 2.3 Cadena de respaldo (lo que se MUESTRA) y qué se marca

1. `rotulo` declarado. `origen: "declarado"`.
2. El nombre de la pieza ligada, si la escribió alguien (no la generó un layout:
   `services/tablero.piezas_del_layout`). Se le quita la designación y el prefijo del
   super-comando: «Interruptor de tapa -B1» → «Interruptor de tapa». `origen: "pieza"`.
3. Un relé de seguridad sin rótulo toma «Seguridad de» + los rótulos de lo que vigila. Sale del
   cableado de S12/S22 (`cosim/modelos/seguridad.py:83`), p. ej. «Seguridad de Parada de
   emergencia y Tapa del tanque». `origen: "derivado"`.
4. El tipo de la ficha + lo que lo distingue en el catálogo: «Pulsador verde», «Piloto ámbar»,
   «Relé de seguridad». `origen: "tipo"`. Nunca la designación sola.

Los comentarios del ST y los nombres de variable NUNCA se muestran como nombre. Sólo entran como
SUGERENCIA en el texto del aviso para el agente («del programa: `marcha`»).

**Qué se marca** [opinión]:
- En el visor, nada distinto: la persona no tiene la culpa de la omisión y «Pulsador verde» se lee
  bien. El respaldo es para MOSTRAR, nunca para APROBAR.
- La falta la ve el MODELADOR en dos lugares, con UN solo criterio (`library/calidad/nombres.py`,
  puro):
  1. `delivery_check` suma la regla «nombres por función» (AVISO), en el bucle que el modelador ya
     corre.
  2. La puerta de publicación suma el ítem `interfaz.nombres_por_funcion` (FALLA, sin
     justificación posible; § 2.5).
- **NO va en el ERC.** `riesgos.electrico` (`registro.py:281`, `puerta.py:187`) falla con
  cualquier aviso del ERC: una falta de nombre saldría como «riesgo eléctrico», que no es, y se
  contaría dos veces.

### 2.4 ¿Todo necesita rótulo? No

[opinión] Tres alcances, de más a menos duro:
- **lo que se maneja**: pulsador, seta, selector, seccionador, resguardo, accionamiento manual de
  una válvula → ítem de la puerta (FALLA);
- **lo que se lee al operar o probar**: pilotos, panel de operador, sensores → ítem de la puerta
  (FALLA);
- **lo repetido**: dos o más aparatos del mismo tipo, donde la designación es lo único que los
  distingue (-K2/-K3, -RZ1/-RZ2, -MM1 si hay otro cilindro) → sólo el AVISO de `delivery_check`.
  Es legibilidad, no identificación funcional de norma: no cabe en una puerta «en piedra».

Un aparato ÚNICO cuyo tipo ya es su función (el PLC, la fuente de 24 V, el variador, la bornera
de tierra, la red) se nombra bien con su tipo. Pedirle rótulo sería relleno.

### 2.5 El ítem de la puerta: `interfaz.nombres_por_funcion`

Se declara como `Entrada` en `REGISTRO` (`library/calidad/registro.py:244-311`):

```python
Entrada("interfaz.nombres_por_funcion",
        "Cada mando, piloto y sensor que la persona opera o ve tiene su nombre por función declarado",
        "el operador acciona el mando equivocado o no sabe qué indica un piloto; quien prueba la "
        "máquina en el visor no la entiende sin el plano",
        "IEC 60204-1 §16.3 (identificación funcional; numeral a confirmar en la F0) · criterio de "
        "diseño", "seguridad",
        hay("operables", "sin mandos, pilotos ni sensores que la persona opere o vea"),
        nb.nombres_por_funcion, "operables")
```

**Alcance determinista.** `services/puerta_hechos.py` (`elementos["operables"]`, junto a
`:140-158`) cuenta los dispositivos del carril cuyo `modelo.tipo` es:
- lo que se opera: `vivo_fotograma.MANDOS` (pulsador, seta, selector, seccionador, resguardo) y
  una electroválvula con `manual`;
- lo que se lee: piloto, hmi;
- sensores: sensor, presostato.

La clase de la evidencia es el tipo (`{"pulsador": 4, "piloto": 4, "resguardo": 2, …}`).
- El tablero que nadie toca (protecciones, PLC, fuente, relés, variador, bornera, motor,
  cilindro) queda FUERA del ítem.
- Sin carril, o sin esos tipos → NO_APLICA con el porqué.

**Qué cuenta como nombre válido.** Se normaliza: minúsculas, sin tildes, espacios colapsados.
Vale si cumple TODO:
1. Está DECLARADO en `add_device.rotulo`. El de la pieza, el del tipo o el del relé derivado
   (§ 2.3) no cuentan.
2. Le queda al menos una palabra de ≥ 3 letras después de quitar:
   - las designaciones del documento (con o sin `-`/`=`/`+`) y todo token con forma de
     designación o borne (`^[-=+]?[A-Z]{1,3}\d+(:\S+)?$`);
   - los tokens de su `ref` y las palabras del `name` de su ficha;
   - los colores (verde, rojo, azul, amarillo, ámbar, blanco, negro, gris);
   - los números, medidas y códigos de contacto (`Ø22`, `24V`, `1NA`, `2NC`);
   - los artículos y conectores (de, del, la, el, los, las, y, con, para, a);
   - los NOMBRES DE TIPO genéricos, una tabla cerrada en `nombres.py`: pulsador, botón, seta,
     selector, conmutador, seccionador, interruptor, resguardo, piloto, lámpara, indicador,
     sensor, detector, presostato, válvula, electroválvula, mando, aparato, dispositivo,
     posición(es).
3. No trae un identificador: `_`, `%`, `:` ni un id de comando o pieza (`\bc\d+`).
4. Es ÚNICO entre los operables (normalizado) del mismo aspecto de función. Dos setas en lados
   distintos se nombran distinto. Las dos fajas de un `insert_project` (=Faja1, =Faja2) pueden
   tener cada una su «Marcha»: el visor las separa por el aspecto.
5. Un SELECTOR declara `estados` para cada posición de su ficha, y una electroválvula con mando
   manual, para cada lado. Cada nombre de estado:
   - tiene ≥ 3 letras;
   - pasa la regla 3;
   - es distinto de su clave cruda («0», «I», «14»);
   - p. ej. «Manual», «Ciclo», «Abre la compuerta».

   Resguardo y seccionador usan los estados por defecto de su tipo si no los declaran.

Ejemplos:

| rótulo | ¿vale? |
|---|---|
| «-Q1» | ✗ |
| «Pulsador» | ✗ |
| «Pulsador verde» | ✗ |
| «PULS-22-VERDE-NA» | ✗ |
| «Pulsador Ø22 verde 1NA» | ✗ |
| «Selector 2 posiciones» | ✗ |
| «rs_ok» | ✗ |
| «Marcha» | ✓ |
| «Paro» | ✓ |
| «Interruptor general» | ✓ («general») |
| «Interruptor de tapa» | ✓ («tapa») |
| «Rearme de seguridad» | ✓ |
| «Parada de emergencia» | ✓ |
| «Tapa del tanque» | ✓ |

[opinión] La tabla de tipos es cerrada a propósito: una palabra de función de verdad («general»,
«tapa», «marcha») nunca está en ella. Un falso ✗ se arregla escribiendo mejor el rótulo, nunca
abriendo la tabla.

**Estado.**
- OK con todos válidos.
- FALLA con la lista de casos, recortada como en `puerta.py`. Cada caso lleva:
  - la designación;
  - el motivo: «sin rótulo», «genérico: «Pulsador verde»», «repetido con -S5», «al selector le
    falta el nombre de la posición «I»»;
  - las piezas, para encuadrar;
  - una `sugerencia`, si la hay: el nombre de la pieza ligada o la variable del PLC conectada, con
    su origen. Es sólo texto: nunca se aplica.
- SIN_EVALUAR si el carril no evalúa (el control revienta → la regla del agregador).
- NO hay justificación posible. `justificadas.py` sólo cubre AVISOS, y aquí falta un dato que el
  modelador PUEDE escribir.

**Máquinas viejas.** Toda máquina con mandos sale FALLA en este ítem hasta que se declaren sus
rótulos. No se inventa el nombre: ni el de la pieza, ni el del ST, ni el del tipo cuentan para
aprobar, aunque se MUESTREN en el visor. La sugerencia del caso acelera la corrección (un
`edit_batch` con los rótulos), pero la escribe el modelador.

---

## 3. Diseño

Criterio: el rol manda, la designación acompaña chica, el control dice su efecto y el estado se
lee de la señal. Sólo piezas existentes: `ItemsAtencion`, `Veredicto`, `<Ayuda>`, `<Pista>`,
tokens `--fs-*`/`--fw-*`, la fila `tb-fila` del Tablero y la tapa de color física.

### 3.1 Mandos — antes (medido)

```
Mandos
[■] -Q1   Seccionador cerrado · también con clic en el 3D          [Abrir]
[●] -S0   Seta de emergencia liberada · también con clic en el 3D  [Presionar]
[●] -S1   Pulsador · también con clic en el 3D                     [Presionar]
[●] -S2   Pulsador · también con clic en el 3D                     [Presionar]
[●] -S3   Pulsador · también con clic en el 3D                     [Presionar]
[●] -S4   Selector · también con clic en el 3D                     [0] [I]      ← ninguna marcada
[ ] -B1   Resguardo cerrado · también con clic en el 3D            [Abrir]
[ ] -B4   Resguardo cerrado · también con clic en el 3D            [Abrir]
Pilotos
(●) -P1   Piloto                                                   Apagado
(●) -P2   Piloto                                                   Apagado
(●) -P3   Piloto                                                   Apagado
(●) -P4   Piloto                                                   Encendido
Lecturas
-K2  Relé de seguridad     Corta la marcha
-K3  Relé de seguridad     Corta la marcha
```

### 3.2 Mandos — después

```
Mandos
⚠ La seguridad corta la marcha                       ← veredicto: sólo hechos leídos de señales
  También los accionas con clic en el 3D.            ← <Pista>, UNA vez

ENERGÍA
[■] Interruptor general            -Q1        [ Apagado | Encendido ]

SEGURIDAD
[●] Parada de emergencia           -S0        Liberada        [Presionar]
[●] Rearme de seguridad ⓘ          -S3        Corta la marcha [Presionar]
[ ] Tapa del tanque                -B1        [ Cerrada | Abierta ]
[ ] Recipiente bajo la descarga    -B4        [ Acoplado | Sin recipiente ]

OPERACIÓN
[●] Marcha                         -S1                        [Presionar]
[●] Paro ⓘ                         -S2                        [Presionar]
[●] Modo                           -S4        [ Manual | Ciclo ]   ← la actual, leída de <des>.posicion

PILOTOS
(●) Marcha                         -P1        Apagado
(●) Falla                          -P2        Apagado
(●) Tapa abierta                   -P3        Apagado
(●) Recipiente no acoplado         -P4        Encendido

LECTURAS
Motor de mezcla                    -M1        0 rpm · 0,0 A
Seguridad de tapa y seta           -K2        Corta la marcha
Seguridad del recipiente           -K3        Corta la marcha
```

Reglas del diseño:
- **El rótulo, en `--fw-medio`.** La designación va en `--fs-chico` y tinta secundaria, a la
  derecha del rótulo, sin negrita ni caja. No se oculta: el electricista la busca.
- **Un mando que SE QUEDA (seccionador, resguardo, selector) es un control segmentado** con los
  nombres de sus `estados`.
  - El segmento marcado es el estado LEÍDO de la señal, no lo último que se tocó.
  - Así no hace falta un verbo genérico («Abrir» un recipiente) y se resuelve la concordancia de
    género: «Cerrada» la declara el modelador. El servidor no adivina.
  - Sin `estados` declarados, el default por tipo vive en el servidor: seccionador
    «Apagado/Encendido»; resguardo «Cerrado/Abierto»; selector, la posición tal cual.
- **Un pulsador con resorte sigue siendo botón con verbo**, porque se mantiene apretado. La seta,
  botón «Presionar/Liberar» (ISO 13850: se suelta girándola).
- **Agrupar por propósito sólo con más de 5 mandos.** La regla es derivada, sin campo nuevo:
  - seccionador → Energía;
  - seta, resguardo y todo mando cableado a una entrada de relé de seguridad → Seguridad
    (-S3 → `-K2:S34`, `-K3:S34`: [dato] del circuito);
  - el resto → Operación.
- **El rearme muestra lo que rearma.** Su estado es el de los relés a los que va cableado
  («Corta la marcha» / «Habilita la marcha»).
- **Un botón que hoy no tendría efecto NO se deshabilita.** Ej.: el rearme con la seguridad ya
  habilitada, o con la tapa abierta. El panel es un BANCO DE PRUEBA: «presiono rearme con la tapa
  abierta y NO debe rearmar» es justo lo que se prueba. Deshabilitarlo escondería esa prueba y
  mentiría si el modelo se equivoca. Se ve en el estado al lado, que no cambia.
- **El veredicto arriba** (pieza `Veredicto`) sólo dice hechos leídos de señales, en orden de
  bloqueo:
  1. «Sin energía» (seccionador abierto);
  2. «Parada de emergencia presionada»;
  3. «<rótulo del resguardo> abierta»;
  4. «La seguridad corta la marcha»;
  5. si no hay nada de eso: «Energía y seguridad habilitadas».

  Nunca «Lista para arrancar»: el permiso del PLC no se conoce y eso mentiría.
- **La ⓘ abre la `descripcion` (N2)**, sólo donde existe. Nada de texto bajo cada fila.
- **El escenario de la apertura** se muestra humanizado («Ciclo nominal»); el id queda en el
  `value`.

### 3.3 Tablero → Aparatos

```
ANTES
-K2   Relé de seguridad 2 canales 24 VDC                    ›
-K3   Relé de seguridad 2 canales 24 VDC                    ›
-P3   Piloto LED Ø22 ámbar 24 V                             ›
-P4   Piloto LED Ø22 ámbar 24 V                             ›
-K1   PLC compacto 14 DI / 10 DO / 2 AI 24 VDC              ›
Calentamiento: El más justo es -Q1: 46 de 50 °C

DESPUÉS
Seguridad de tapa y seta      -K2 · Relé de seguridad 2 canales       ›
Seguridad del recipiente      -K3 · Relé de seguridad 2 canales       ›
Tapa abierta                  -P3 · Piloto LED Ø22 ámbar              ›
Recipiente no acoplado        -P4 · Piloto LED Ø22 ámbar              ›
PLC compacto 14 DI / 10 DO    -K1                                     ›   ← único: el tipo basta
Calentamiento: El más justo es el interruptor general (-Q1): 46 de 50 °C
```

### 3.4 Simular falla

```
ANTES                                        DESPUÉS
Aparato [ -K2 · Relé de seguridad ▾ ]        Aparato [ Seguridad de tapa y seta · -K2 ▾ ]
        [ -K2:13-14 · Contacto      ]                [ Contacto 13-14 · Seguridad de tapa y seta ]
        [ c160 · Cable              ]                [ Cable Red L1 → Interruptor general ]
```

El cable sin designación se nombra por sus EXTREMOS (los rótulos de sus dos aparatos), nunca por
el id del comando.

### 3.5 Neumática y accionamiento manual

```
ANTES
-QM1   Sin accionar · posición 14                 [Accionar a mano · 14]
-MM1   Ø32 mm, vástago 12 mm · carrera 200 mm
-RZ1   Regulador de caudal        -RZ2   Regulador de caudal
⚠ El vástago de -MM1 pandea: admite 17,6 kN contra 483 N        ← falso (FS 109)

DESPUÉS
Válvula de la compuerta   -QM1   Cierra la compuerta         [Accionar a mano]
Cilindro de compuerta     -MM1   Ø32 · vástago 12 · carrera 200 mm
Caudal de apertura  -RZ1         Caudal de cierre  -RZ2
⚠ Falta el límite elástico del vástago del cilindro de compuerta (-MM1)
```

### 3.6 Pruebas, Eventos, Cinemática y Señales

- **Pruebas**: el título es el `nombre` humanizado («Descargar sin recipiente»: `_` → espacio,
  mayúscula inicial). Es derivado: no hace falta campo nuevo. La `descripcion` se escribe para la
  persona; `set_scenario` avisa si trae ids de comando o pieza (`c\d+…`).
- **Eventos y Cinemática**: la junta se nombra por su pieza HIJA («Eje de paletas»,
  «Tapa de carga», «Puerta del tablero»), derivada de `child`; el `name` va secundario.
- **Señales**: la cabecera de cada aparato es «rótulo · -K2». Las hojas (los nombres de señal) no
  cambian.

### 3.7 Cuándo basta la designación (la premisa, cuestionada)

[opinión] La designación sola está bien donde el CONTEXTO ya dice qué es o donde el usuario está
haciendo trabajo de cableado:
- la etiqueta 3D sobre la pieza;
- la lista de conductores borne a borne;
- las hojas de «Señales»;
- el texto del PLC;
- el esquema, que la norma rotula con designación.

En el resto, si la persona tiene que ACTUAR o DECIDIR sobre el aparato, el rótulo manda.

---

## 4. La regla (líneas exactas)

### `ui/CLAUDE.md`, en § Texto y ayuda, tras «Lo técnico suma detalle a pedido»

```
- **Un aparato se nombra por lo que HACE** («Marcha», «Tapa del tanque»): en toda fila, opción o
  frase que lo nombra manda su rótulo y la designación IEC va detrás, chica (`-S1`). Rótulo,
  estados y respaldo los decide el servidor (`services/rotulos.py`), nunca una tabla de la UI; sin
  rótulo cae al tipo («Pulsador verde»), jamás a la designación sola ni a un id de comando. Un
  mando que se queda (seccionador, resguardo, selector) es un control segmentado con sus estados,
  leídos de su señal, y un mando no se deshabilita por no tener efecto ahora: el panel es un banco
  de prueba. [nombres-por-funcion](../docs/plans/nombres-por-funcion.md)
```

### `core/apolo/library/electrico/CLAUDE.md`, en § La ficha de una ref (o § Modelo y ERC)

```
- **Rótulo de un aparato** (`add_device.rotulo`/`estados`/`descripcion`, en `Dispositivo` y
  fuera de la firma): lo que HACE para quien opera, el texto de su placa de leyenda; `estados`
  nombra las posiciones de SU ficha y se valida contra el modelo, como `ajustes`. Lo exige el
  ítem `interfaz.nombres_por_funcion` de la puerta (lo que se opera o se lee) con el criterio de
  `calidad/nombres.py`, nunca el ERC; el respaldo que se MUESTRA (pieza, relé por lo que vigila,
  tipo) es de `services/rotulos.py`, no aprueba y nunca lee el ST.
  [nombres-por-funcion](../../../../docs/plans/nombres-por-funcion.md)
```

### `core/apolo/design/guidelines.py`, entrada `electrico`

El `corto` entra al brief de TODA sesión: se agregan tres palabras.

```python
"corto": "Si la máquina lleva tablero: cada motor con su protección, parada de "
"emergencia, masas a tierra, designaciones IEC 81346 con su rótulo y colores IEC 60204-1.",
```

Al `detalle`, al final:

```python
"Cada mando, piloto y aparato repetido lleva `rotulo`: lo que hace para el operador, el texto "
"de su placa («Marcha», «Rearme de seguridad», «Tapa del tanque»), nunca la designación ni la "
"ref. Un selector, un resguardo o una electroválvula con mando manual lleva `estados` con el "
"nombre de cada posición ({\"0\": \"Manual\", \"I\": \"Ciclo\"}); `descripcion`, una frase, "
"sólo si el rótulo no lo dice todo."
```

Al `verificar`:

```python
"verificar": "electrical_check (ERC) + get_circuit; en el lote que cablea, el contrato "
"{\"erc\": \"sin_errores\"}; delivery_check lo incluye y avisa los aparatos sin rótulo.",
```

### `core/apolo/library/CLAUDE.md`, en § Validación, junto a la puerta de publicación

```
- `interfaz.nombres_por_funcion` (`calidad/nombres.py`, puro; filas de `services/rotulos.py`):
  cada mando, piloto y sensor DECLARA su rótulo por función (`add_device.rotulo`) y el selector
  sus `estados`; lo derivado (pieza, ST, tipo) se muestra pero NUNCA aprueba, y no hay
  justificación (es un dato que se escribe). La tabla de tipos genéricos es cerrada: no se abre
  para aprobar un rótulo. [nombres-por-funcion](../../../docs/plans/nombres-por-funcion.md)
```

Opcional, en `core/apolo/cosim/CLAUDE.md` (escenarios):

```
- La `descripcion` de un escenario la lee una persona en «Pruebas»: sin ids de comando ni de
  pieza (`set_scenario` avisa); el título es su `nombre` humanizado. [nombres-por-funcion](…)
```
