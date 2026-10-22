---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: aprobado por Mario (2026-10-21) con la cola de YouTube en la tienda (D5); F1 implementada con tests (falta su verificación real — Mario autoriza el canal «Apolo CAD» en el navegador y sube un video privado — y, tras ella, pedir la auditoría, D11); T entregada (PED-125); F2 implementada con tests y los briefs escritos en apolo-fabrica (falta que Mario los revise y los commitee allá, y verla con una ficha escrita por un modelador real en F4); F3 implementada con tests (la fábrica, el subidor de la cola y su tarea diaria; falta correrlos de verdad contra la tienda y YouTube, lo que hace F4); ajuste D10 (la máquina andando con producto en el video de la fábrica) implementado con tests, falta verlo en un video real; faltan F0 y F4
descripcion: Mario pide «crea estas máquinas» y Apolo entrega cada una modelada, revisada, con su video en YouTube y publicada en apolocad.com, sin pasos a mano
---

# Pides máquinas y salen publicadas en YouTube y en la tienda

## Estado y origen

Mario (2026-10-21): «recuerda que esto es automático, yo te pido a ti crea máquinas (de una a
uno o varias en paralelo), genera un video (con acabados realistas de cómo se arma), súbelo a
YouTube (con su descripción para ir a apolocad.com) y súbelo también a apolocad.com. ¿Qué nos
falta para eso?». Sobre las respuestas: «sobre el punto 3 tú encárgate, sólo pásame un par de
videos para ver cómo queda y te ajusto»; «por ahora no vamos a tener videos realistas que
demoren horas»; YouTube «tiene que ser automático», en un canal propio, no el personal.

Evidencia que lo disparó: la primera subida real a la tienda con `publicar subir` (PED-123 +
F6 de [publicacion-tienda](publicacion-tienda.md), 2026-10-21) funcionó de punta a punta; lo
que queda manual está medido abajo.

## Lo que hay hoy

| paso | hoy | dónde |
|---|---|---|
| modelar varias a la vez | `scripts/flota.py` + `claude -p` por puerto; F4 (tres a la vez) sin correr | [varias-maquinas-a-la-vez](varias-maquinas-a-la-vez.md) |
| revisión de taller | subagente ciego, prompt generado | [revisor-de-taller](../revisor-de-taller.md) |
| guion y ficha | `publicar guion` escribe `guion.json` y un BORRADOR de `ficha.yaml`; descripción, etiquetas y `url_tienda` los llena una persona (`flujo.py:186-189`, `ficha.py:61-78`) | `core/apolo/publicacion/` |
| video realista | `generar --render navegador` (nivel rápido: 65 s de video en 7 min en una Intel UHD, nota de [video-realista](video-realista.md)); `--nivel maximo` tarda horas | idem |
| música | `--musica <archivo>` a mano, con los datos de la pista en `ficha.yaml` (D8 de video-tienda-pulido) | `scripts/publicar.py:83` |
| YouTube | MANUAL: `generar` deja `youtube.txt` y pide subirlo a mano (`flujo.py:489-490`) | `textos.py:178` |
| tienda | `publicar subir` (llave `APOLO_TIENDA_LLAVE`) | `publicacion/tienda.py` |
| encadenado | no existe: cada paso es un comando y entre ellos hay una persona | — |

Ya hecho fuera del repo (2026-10-21): canal de YouTube «Apolo CAD» (cuenta de marca, verificado
por teléfono → miniaturas propias), proyecto de Google Cloud `apolo-publicador` con la YouTube
Data API v3, pantalla de permiso externa EN PRODUCCIÓN (sin verificar) y un cliente OAuth de
escritorio cuyo JSON está en `~/.apolo/youtube/client_secret.json`. La tienda tiene en curso
PED-124 (términos, privacidad y aviso de responsabilidad, con `/terminos#responsabilidad`).

## Lo que se revisó antes de escribir esto

- `textos.youtube()` ya arma título, descripción con capítulos, etiquetas y la línea de
  música; sólo falta que alguien lo suba. `url_tienda` es derivable: `<tienda>/maquinas/<slug>`.
- `flujo.py:438-440` ya pone `url_tienda` en el cierre del video si la ficha la trae.
- La tienda NO lee `url_video` (búsqueda en el código de `apolo`: sin coincidencias); su ficha
  muestra el video desde R2. Un enlace a YouTube en la tienda es otro pedido, y no hace falta.
- YouTube deja PRIVADO todo video subido por la API desde un proyecto no auditado; el cupo por
  defecto es 10 000 unidades/día y una subida cuesta ~1 600 (≈ 6 por día). La auditoría
  («YouTube API Services Audit») levanta las dos cosas.

## Decisiones (para vetar)

- **D1 — El que redacta la ficha es el modelador.** Al terminar la máquina, el mismo agente que
  la modeló (conoce la función, la carga y las decisiones) completa `ficha.yaml`: descripción,
  etiquetas, nivel y precio. `url_tienda` deja de ser campo humano: se deriva del slug y de la
  tienda. `publicar ficha --revisar` valida con `ficha.validar` y la fábrica no avanza con
  errores. Porqué: otro agente tendría que releer todo el modelo para escribir peor lo mismo.
- **D2 — Video «realista normal», nunca el máximo.** La fábrica usa `--render navegador --nivel
  rapido`: minutos, también en la laptop. Sin navegador o sin GPU cae a VTK y lo dice (lo que ya
  hace `generar`). El trazado de rayos sigue existiendo, sólo a mano.
- **D3 — Cliente de YouTube propio con httpx + stdlib, sin dependencias nuevas.** OAuth de app
  instalada (loopback en `127.0.0.1`, PKCE), token de refresco en `~/.apolo/youtube/token.json`
  (fuera del repo, nunca al log), subida reanudable con avance y reintento, miniatura con
  `thumbnails.set`. Las bibliotecas de Google traen ~10 paquetes para tres llamadas HTTP.
- **D4 — Privado hasta la auditoría.** La fábrica sube con `privacyStatus: private` y
  `selfDeclaredMadeForKids: false`; un flag `--publico` existe para después de la auditoría. El
  reporte final dice qué videos esperan el clic de Mario en YouTube Studio. Pedir la auditoría
  (formulario de Google) es tarea de Mario al cerrar F4.
- **D5 — YouTube es una cola aparte y la cola vive en la TIENDA** (Mario, 2026-10-21: «creamos
  las máquinas en apolo y lo subimos a la página apolocad.com y ponemos en cola para youtube…
  vamos a tener varias pcs de escritorio… el cuello de botella será en youtube»). Una máquina
  está TERMINADA cuando queda publicada en la tienda; YouTube no la frena. El cupo de YouTube es
  UNO por proyecto de Google para todas las PCs, así que la cola no puede ser un archivo de cada
  PC: la tienda ya tiene cada máquina y su video en R2. Un único «subidor»
  (`publicar youtube --cola`) pide a la tienda las máquinas publicadas sin video en YouTube,
  baja el video y la miniatura de la tienda, los sube y anota en la tienda el id y el estado; al
  agotar el cupo (`quotaExceeded`) para y sigue al día siguiente (tarea programada diaria). Esto
  necesita un pedido de la tienda (Fase T). Mientras no exista, `publicar youtube` sube desde la
  carpeta local.
- **D6 — La fábrica es idempotente por pasos y termina en la tienda.** `publicar fabrica
  --project N` hace guion → ficha revisada → generar → tienda y deja `estado.json` en la carpeta
  de la versión; si algo falla, volver a correrla retoma desde el paso que falló. No toca
  YouTube: eso es la cola (D5).
- **D7 — Varias máquinas y varias PCs: producir en paralelo, una sola cola.** Los modeladores
  corren a la vez con `flota.py` (cada uno su API); en cada PC la fábrica toma un candado de
  archivo para la grabación del video (una GPU). Cada PC tiene su propia llave de la tienda
  (PED-123: máx. 5 por persona). El subidor de YouTube corre en UNA sola PC. El orquestador es
  la sesión de Claude con la que habla Mario: lanza modeladores, el revisor ciego y la fábrica.
- **D11 — Pedir la auditoría de YouTube apenas F1 suba el primer video real.** Con varias PCs el
  cupo (~6 subidas/día) es EL cuello de botella; la auditoría lo sube y permite videos públicos.
  Mientras tanto la cola absorbe la diferencia.
- **D8 — El aviso de responsabilidad viaja con el video.** La descripción de YouTube suma
  «Diseño generado y validado por software: no fue construido ni probado físicamente.» con el
  enlace a `/terminos#responsabilidad` (PED-124), y el cierre del video lleva la misma línea en
  el rótulo final.
- **D9 — Biblioteca de música local.** Mario baja pistas (Pixabay Music: uso comercial sin
  atribución) a `~/.apolo/musica/` y las describe en `pistas.json` (archivo, título, autor,
  fuente, licencia). La fábrica elige la menos usada y llena `ficha.musica`; sin pistas, el
  video sale sin música y lo avisa.
- **D10 — Mario ve los dos primeros.** F4 entrega dos máquinas reales; lo que Mario ajuste
  (ritmo, rótulos, encuadres, texto) entra como cambio al guion o a los textos, no como paso
  manual permanente.

- **D12 — Código público, receta privada** (Mario, 2026-10-21, ante el riesgo de que alguien
  compita con otra tienda y otro canal; Apolo CAD sigue MIT). El código genérico (`publicar
  subir`, `youtube`, `fabrica`, la cola) va en este repo: no da ventaja (se copia en días) y lo
  usarán los creadores de la parte 3. Los briefs de producción (modelador + «redacta la ficha»,
  orquestación de varias máquinas y PCs), los criterios de qué máquinas hacer y `pistas.json`
  van al repo PRIVADO `apolo-fabrica` (hermano de este checkout). El revisor de taller se queda
  público: es parte del producto. Credenciales en ningún repo (`~/.apolo/` de cada PC).

## Alternativas descartadas

- **google-api-python-client + google-auth-oauthlib**: funciona, pero suma dependencias al
  paquete de PyPI para tres llamadas (D3).
- **Un agente «redactor» aparte para la ficha**: relee el modelo entero; el modelador ya lo tiene
  en contexto (D1).
- **Subir público con una cuenta de servicio**: YouTube no acepta cuentas de servicio para
  subir a un canal.
- **Mostrar el video de YouTube en la tienda**: la tienda ya sirve su video desde R2; un enlace
  a un video privado no sirve. Si hace falta tras la auditoría, es un pedido de la tienda.

## Fases

- **F0 — Medir (sólo lectura, S).** Una máquina existente por la cadena actual a mano, con
  tiempos por paso en la laptop (guion, generar navegador rápido, subir tienda). Confirmar en la
  consola de Google el costo real de `videos.insert` y el cupo. Sale la tabla de tiempos que
  usa F3 para el reporte.
- **F1 — Cliente de YouTube (M, `core/apolo/publicacion/youtube.py` + `publicar youtube`).**
  OAuth loopback (primera vez abre el navegador; Mario elige el canal «Apolo CAD»), token de
  refresco, subida reanudable, miniatura, privacidad (D4), `quotaExceeded` como estado y no como
  falla, `youtube.json` en la carpeta. Sube desde la carpeta local de un paquete ya generado.
  Tests con un servidor falso de OAuth y de YouTube (como `tests/test_publicar_tienda.py`).
  Verifica: un video real subido privado al canal, con miniatura y descripción.
- **T — La cola en la tienda (pedido de Caronte, en paralelo con F2).** En la máquina: id de
  YouTube, estado (`pendiente`, `subido`, `fallo`) y fecha; con la llave de publicación,
  `GET` de las máquinas publicadas pendientes (con la dirección de su video y su miniatura) y
  `PUT` para anotar el resultado; en Máquinas, una columna con el estado de YouTube. Va en el
  orden de PED-124 (no lo pisa).
- **F2 — Ficha y textos automáticos (M, `publicacion/`).** `url_tienda` derivada; `publicar
  ficha --revisar`; aviso de responsabilidad en la descripción y en el cierre (D8); biblioteca
  de música (D9); el brief del modelador suma la sección «redacta la ficha» (D1) y el orden de la
  orquestación (D7), en el repo privado `apolo-fabrica` (D12); aquí sólo el código. Depende de PED-124 sólo por el
  enlace `/terminos`. Verifica: tests de textos y de ficha; una ficha escrita por un modelador
  pasa `--revisar`.
- **F3 — La fábrica y el subidor (M, `publicacion/fabrica.py` + `publicar fabrica` y `publicar
  youtube --cola`).** La fábrica encadena guion → ficha → generar → tienda con `estado.json` y
  reanudación (D6) y candado de render (D7); el subidor vacía la cola de la tienda hasta el cupo
  (D5) y su tarea programada diaria. Reporte final: tiempos, URL de la tienda, cuántos esperan
  en la cola de YouTube y qué falta que haga Mario. Depende de F1, F2 y T. Verifica: tests con
  servicios falsos y un corte a mitad que retoma.
- **F4 — Dos máquinas de verdad (verificación, con Mario).** Dos máquinas nuevas en paralelo con
  `flota.py` (cierra también la F4 de varias-maquinas con dos modeladores), revisor ciego,
  correcciones y `publicar fabrica` de cada una. Mario ve los dos videos y la ficha; sus ajustes
  vuelven a F2/F3. Al cerrar: Mario pide la auditoría de YouTube.

- **F5 — El corto vertical (shorts y reels) (M, aprobado por Mario 2026-10-21).** Además del
  video largo, cada máquina saca un corto 9:16 de 20–40 s: en los primeros 2 s la máquina
  terminada (andando si hay marcha), luego el armado rápido y al final la portada con
  apolocad.com. Va a la cola de YouTube como Short (cuenta como otra subida: con el cupo sin
  auditar baja a ~3 máquinas/día) enlazado al largo como «video relacionado» (los enlaces de la
  descripción de un Short no se pueden cliquear); el mismo archivo sirve para Instagram Reels y
  TikTok (a mano al principio). Se arma después de que Mario ajuste los dos videos de F4, para
  heredar el ritmo. Depende de F4 y de la cola (T): la tienda tiene que distinguir el largo del
  corto (pedido de Caronte).

## Lo que este plan NO hace

- Videos con trazado de rayos (D2), ni música generada por IA.
- Pasar los videos a público solos antes de la auditoría (D4).
- Cambios en la tienda fuera de la cola (Fase T): el enlace a YouTube en la ficha queda fuera;
  los términos están en PED-124.
- Decidir QUÉ máquinas se hacen: eso lo pide Mario.

## Riesgos

- **El token de YouTube es una credencial**: vive en `~/.apolo/youtube/`, fuera del repo; nunca
  se imprime ni se loguea; los tests usan servidores falsos. Si se filtra, se revoca en la
  cuenta de Google (Seguridad → Apps con acceso).
- **Un video que YouTube marca por derechos de autor** (música): sólo pistas con licencia de
  `pistas.json` (D9); la descripción cita la pista.
- **Una máquina mal modelada llega a YouTube**: la fábrica exige la puerta de entrega en VERDE
  (como `generar`) y el revisor ciego corre antes; los videos salen privados (D4), así que Mario
  ve todo antes de que sea público.
- **Cupo diario**: la cola (D5) y el reporte dicen cuántos esperan.

## Bitácora

### F1 — cliente de YouTube (2026-10-21, implementada; falta la subida real)

```powershell
.\.venv\Scripts\python.exe -B scripts\publicar.py youtube --slug S [--version V] [--publico] [--ensayo] [--forzar] [--reautorizar]
```

- `publicacion/youtube_oauth.py` (permiso) y `publicacion/youtube.py` (subida) en dos módulos:
  uno solo pasaba de las 500 líneas y son dos responsabilidades. httpx + stdlib (D3).
- **Credenciales**: `paths.home()/youtube` (`APOLO_HOME` o `~/.apolo`), `APOLO_YOUTUBE_DIR`
  la cambia. `token.json` guarda SÓLO el token de refresco, los scopes y el canal (el access
  token vive en memoria; se refresca en cada corrida, es una llamada). Se escribe con 0600 vía
  temporal + `os.replace`. Ningún mensaje lleva client_secret, código ni tokens (`_ocultar` en
  los errores de Google; la URL de autorización sólo trae el client_id, que no es secreto).
- **OAuth**: loopback `http://127.0.0.1:<libre>/` con `HTTPServer` que atiende pedidos hasta
  recibir `code` o `error` (un `favicon` no lo corta), 5 min de espera, PKCE S256, `state`
  comparado con `compare_digest`, `access_type=offline` + `prompt=consent`. Si el permiso
  llega sin la casilla de subir (consentimiento granular) o sin refresh token, lo dice y pide
  `--reautorizar`. `invalid_grant` al refrescar → `SinAutorizacion` con `--reautorizar`.
  Extremos: parámetro > variable (`APOLO_YOUTUBE_API`, `APOLO_YOUTUBE_UPLOAD`,
  `APOLO_GOOGLE_TOKEN_URL`, `APOLO_GOOGLE_AUTH_URL`) > `client_secret.json` > Google.
- **Textos, una fuente**: `textos.datos_youtube(ficha, capitulos, musica)` → {titulo,
  descripcion, etiquetas}; `textos.youtube()` (el `youtube.txt`) la envuelve y la subida la usa
  con lo de `ficha.json` (capítulos y crédito de `video`). Cambio de paso: `youtube.txt` ya no
  acredita la música de `ficha.yaml` si el video salió sin ella (usa el mismo crédito que
  `ficha.json`). Sin `url_tienda` en la ficha, la subida deriva `<tienda>/maquinas/<slug>`
  (`--tienda`/`APOLO_TIENDA_URL`); `youtube.txt` sigue igual hasta F2.
- **Subida**: se dice el canal antes de subir; sesión reanudable con los metadatos (categoría
  28, `es`, privado salvo `--publico`, `selfDeclaredMadeForKids: false`); trozos de 8 MiB desde
  disco; un 5xx o un corte espera con backoff (2 s × 2ⁿ, tope 60 s, 6 seguidos) y pregunta
  `bytes */total` antes de seguir; un 401 renueva el access token una vez; un 404 de la sesión
  = venció, se empieza de cero. Miniatura > 2 MB o rechazada = aviso, el video queda.
  `quotaExceeded`/`uploadLimitExceeded`/`dailyLimitExceeded` → `CupoAgotado` sin
  `youtube.json`. `youtube.json` existente → no resube salvo `--forzar` (ni pide permiso).
  `--ensayo` sí obtiene el permiso (sirve para autorizar la primera vez sin subir).
- Tests: `tests/test_publicar_youtube.py` (17, Google falso en un hilo; el navegador simulado
  vuelve al loopback con código y `state`).
- **Sin verificar contra Google** (sólo con el falso): que el loopback `127.0.0.1` con barra
  final se acepte como `redirect_uri` de un cliente de escritorio; la forma exacta del 308
  (`Range`) y del error de cupo; que `thumbnails.set` acepte el PNG por POST con el cuerpo
  crudo; que el 401 con la sesión abierta se arregle renovando el token. Lo confirma la subida
  real con Mario.

### T — la cola en la tienda (PED-125, entregado 2026-10-21, revisión sin bloqueantes)

Contrato para el subidor (F3), todo con `Authorization: Bearer apolo_pub_…` y `MAQUINA_GESTIONAR`;
errores `{error}`:
- `GET /api/maquina/youtube/cola?limite=N` (1–20, 6 por defecto) → `{ok, maquinas: [{id, slug,
  titulo, url, estado, intentos, video: {url, bytes, sha256}, miniatura: {url, bytes} | null,
  youtube: {titulo, descripcion, etiquetas, origen: "paquete" | "por_defecto"}}]}`, de la más
  antigua; entran publicadas con video vigente en `pendiente`, `fallo` con < 3 intentos o
  `subiendo` con la reserva (3 h) vencida.
- `POST /api/maquina/<id>/youtube/reserva` (sin cuerpo) → `{ok, maquina, reservada_hasta}`;
  atómica; 409 = otro la tomó / ya subida / no disponible → pedir la cola y tomar otra.
- `PUT /api/maquina/<id>/youtube` con `{resultado: "subido", video_id (11, [A-Za-z0-9_-]), url
  (https://www.youtube.com/… o https://youtu.be/…), privacidad (private|unlisted|public)}` |
  `{resultado: "fallo", error}` (suma intento; 3 = fuera) | `{resultado: "cupo"}` (vuelve a
  pendiente sin intento). 409 si `fallo`/`cupo` sobre una no reservada; `subido` se acepta
  siempre que haya entrado a la cola.
- Bloque `youtube` de `ficha.json` (opcional): `{titulo (1–100), descripcion (≤ 5000 BYTES
  UTF-8), etiquetas (lista; suma con comas y comillas ≤ 500)}`, sin `<` ni `>`; si no cumple se
  guarda null en silencio y la tienda arma textos por defecto. → F2 debe validar con los MISMOS
  límites antes de generar, para no caer en silencio al texto por defecto.

### F2 — ficha y textos automáticos (2026-10-21, implementada con tests)

```powershell
.\.venv\Scripts\python.exe -B scripts\publicar.py ficha --project N --revisar [--slug S] [--version V] [--tienda URL]
.\.venv\Scripts\python.exe -B scripts\publicar.py generar --project N [--musica X | --sin-musica] [--tienda URL]
```

- **Una fuente, validada antes de trabajar**: `textos.datos_youtube` arma {titulo, descripcion,
  etiquetas} y `textos.problemas_youtube` aplica los límites de T. `generar` lo valida al
  empezar (con los capítulos del guion y la música elegida: falla antes de la puerta y del
  video, sin tocar la carpeta) y otra vez al armar el paquete, y escribe el MISMO dict en
  `youtube.txt` y en el bloque `youtube` de `ficha.json`; `publicar youtube` sube ese bloque tal
  cual (un paquete de antes lo arma como en F1). «Caracteres» = unidades UTF-16 (`length` de
  JavaScript: un emoji cuenta 2), nunca menos de lo que cuenta la tienda; la descripción en
  bytes UTF-8; etiquetas = letras + una coma entre cada una + 2 por las que llevan espacios.
  `ficha.validar` cuenta igual (descripción ≤ 3000 BYTES, etiquetas ≤ 500 con esa suma).
- **`url_tienda` derivada** (`textos.url_maquina`: `<tienda>/maquinas/<slug>`; la tienda,
  `tienda.url_de_la_tienda`: `--tienda` > `APOLO_TIENDA_URL` > apolocad.com). El borrador de
  ficha.yaml ya no la trae y `validar` la acepta como opcional (las fichas de antes la tienen);
  una escrita a mano que no coincide se avisa y gana la derivada. `guion` la escribe en
  `cierre.url`; `generar` la pone en la ficha, el LEEME, la licencia, ficha.json, el cierre (si el
  guion trae otra, lo avisa) y la descripción.
- **Aviso (D8)**: la descripción suma «Diseño generado y validado por software: no fue
  construido ni probado físicamente. Antes de fabricar, lee el aviso:
  `<tienda>/terminos#responsabilidad`», después del enlace a la máquina. El cierre del video
  lleva una línea corta equivalente en letra chica (`composicion.AVISO_CIERRE`), dibujada por
  `composicion.cierre`, que usan VTK (`publicacion/video.py`) y el navegador
  (`media/tarjetas.py`): sin tocar `ui/`.
- **Rótulos cortos**: el título de etapa nombra los DOS grupos que más pesan, en su orden
  («Cadenas y motorreductor», el segundo en minúscula; « · » si uno ya lleva «y»), nunca una
  lista de tres ni «y 2 más»; si no caben en 32, el que más pesa. Los capítulos de YouTube son
  esos títulos. El rótulo cuenta por rol y una pieza suelta va por su rol con artículo
  (`rotulos.con_articulo`: «4 patas, 2 travesaños, el motorreductor y la placa base»), nunca por
  su nombre con lados y ejes. El paso de montaje sin grupo se titula con sus dos bases con más
  piezas («Pata y travesaño»), no «Pata y 3 más» (también lo lee el manual). Sobre el `.apolo`
  saneado de la primera publicación real (proyecto 2), hoy salen «Bastidor», «Rodillos» y
  «Cadenas y motorreductor» (el guion de entonces decía «Patas y travesaños, Motorreductor y 2
  más»). Tests golden/guion actualizados: los textos «Se suman «Base» y «Torre».» y «P1 y Otra»
  pasaron a «la base y la torre» y «P1 y otra».
- **Miniatura**: lleva el TÍTULO de la ficha (el guion con el título por defecto —el nombre del
  proyecto, a menudo el slug— lo toma de la ficha también para la portada:
  `preparar.guion_para_video`) y la marca «Apolo CAD». `composicion.maquetar_miniatura` elige la
  letra más grande con la que el título entra ENTERO en 2 líneas (o en 3 con letra ≤ 1.0), sin
  «…», palabras partidas ni una última línea de 1–3 letras («2 / m»); 1280×720 y ≤ 2 MB como
  antes (`guardar_miniatura`). La tienda usa el mismo archivo (rol `miniatura`): sin cambios.
- **Música (D9)**: `publicacion/musica.py`. Biblioteca en `paths.home()/musica`
  (`APOLO_MUSICA_DIR`); `pistas.json` lo escribe una persona y nunca se reescribe; los usos van
  en `usos.json` al lado (sólo se anotan si el paquete salió). Orden: `--musica` >
  `musica.archivo` de ficha.yaml > la menos usada de la biblioteca (a igualdad, la primera) >
  sin música, avisado; `--sin-musica` fuerza silencio. Una biblioteca rota (pista sin
  licencia, archivo ausente, clave desconocida) es un error con todos los problemas. La suite
  apunta `APOLO_MUSICA_DIR` a una carpeta vacía (`conftest.py`) para no usar ni sumar usos a la
  biblioteca real.
- **`publicar ficha --revisar`** (`preparar.revisar`): valida ficha.yaml (además, etiquetas no
  vacías y slug/versión de la carpeta), deriva la URL, elige la música que tocaría (sin anotar),
  arma el texto con los capítulos de `guion.json` y lo imprime con lo que pesa; sale con 2 y los
  problemas si algo falla. No abre el proyecto (con `--project` sólo lee su nombre).
- Lo de `generar` que no es flujo se fue a `publicacion/preparar.py` y las versiones a
  `paquete.py` (`version_libre`, `version_pendiente`): `flujo.py` quedaba sobre 500 líneas.
- **Briefs (D12)**: `briefs/modelador.md` (modelar por MCP + redactar la ficha + `ficha
  --revisar` hasta verde) y `briefs/orquestacion.md` (encargo, flota, revisor ciego,
  correcciones, publicar, cola de YouTube; `publicar fabrica` marcado como F3) en el repo
  privado `apolo-fabrica`; nada de eso va en `docs/`.
- Tests: `tests/test_publicacion_ficha_auto.py` (límites, URL, aviso, música, miniatura, cierre)
  y casos nuevos en `test_publicacion_e2e.py` (bloque youtube en ficha.json, falla temprana de
  `generar`, biblioteca y `--sin-musica`, `ficha --revisar` por el CLI), `test_video_pulido.py`
  (títulos de muchos grupos, rótulo por rol) y `test_publicar_youtube.py` (el bloque va tal cual).

### F3 — la fábrica y el subidor (2026-10-21, implementada con tests)

```powershell
$env:APOLO_TIENDA_LLAVE = 'apolo_pub_...'
.\.venv\Scripts\python.exe -B scripts\publicar.py fabrica --project N [--url U] [--slug S] [--version V] [--tienda T] [--render navegador|vtk] [--borrador] [--desde guion|ficha|generar|tienda] [--sin-esperar]
.\.venv\Scripts\python.exe -B scripts\publicar.py youtube --cola [--limite N] [--tienda T] [--publico] [--ensayo] [--reautorizar]
.\.venv\Scripts\python.exe -B scripts\publicar.py youtube --cola --instalar-tarea [--hora 02:30]
.\.venv\Scripts\python.exe -B scripts\publicar.py youtube --cola --quitar-tarea
```

- **Fábrica** (`publicacion/fabrica.py`): guion (sólo si falta `guion.json`: lo normal es que
  el modelador ya lo corrió al redactar la ficha) → `preparar.revisar` (en rojo PARA y dice que
  la ficha la completa el modelador, D1) → `flujo.generar` con navegador y nivel rápido (D2; si
  el video sale con VTK, lo avisa; con `ficha.json` en la carpeta ya está generado y no se
  rehace) → `tienda.subir`. Cada paso en `estado.json` de la carpeta de la versión: hecho/fallo,
  inicio, segundos, `datos` y las últimas 15 líneas de su salida (la llave, enmascarada). Al
  volver a correrla salta lo hecho; `--desde` borra ese paso y los siguientes del estado. Un
  error con mensaje (RuntimeError, ValueError, OSError: los de la publicación) para con
  `FabricaError`; otro se anota y sube con su traza. La llave se exige ANTES del primer paso si
  la tienda está pendiente (no tras minutos de video). Sin `--version`: la versión con la
  fábrica a medias, con `--desde` la última que pasó por ella, la única con guion sin generar o
  1.0.0 (`version_libre`). No toca YouTube (D5): el reporte da tiempos por paso, la URL y si
  quedó publicada (entra sola a la cola) o en borrador (no entra).
- **Candado de render** (`publicacion/candado.py`, D7): JSON en `paths.home()/render.lock`
  (`APOLO_CANDADO_RENDER`; la suite lo apunta a una carpeta temporal en `conftest.py`) con pid,
  PC, qué se graba, desde y vence (3 h). Se crea con `O_EXCL`; uno vencido o de un proceso
  muerto de esta PC se aparta con un rename (atómico: entre dos, gana uno) y se toma. Ocupado:
  espera avisando cada 2 min, o `--sin-esperar` falla. Envuelve TODO `generar` (entregables
  incluidos: es lo simple, y en la laptop la CPU también es el cuello). En Windows la vida del pid
  se mira con `OpenProcess`, nunca con `os.kill(pid, 0)`: ahí la señal 0 es CTRL_C_EVENT.
- **Subidor** (`publicacion/cola_youtube.py`, D5) con el contrato de T. Reutiliza el
  `tienda.Cliente` (antes `_Tienda`; suma `bajar`, por trozos, con el Bearer sólo en el origen
  de la tienda) y el cliente de F1, partido en `youtube.conectar` (permiso + canal, una vez por
  lote y sólo si hay algo que subir) y `youtube.subir_video` (sube con los textos dados TAL
  CUAL; `subir` de F1 los usa igual). Por máquina: ¿ya subida? (registro `subidas.json` en la
  carpeta del permiso, por sha256 del video, o una carpeta local del mismo slug con
  `youtube.json` y el MISMO video según el sha256 de su `ficha.json`) → reserva (409 = saltar)
  → baja video y miniatura a un temporal (bytes y sha256 del video; una miniatura que no baja o
  no pesa lo dicho sube el video sin ella, con aviso) → sube → anota `subidas.json` ANTES de
  avisar `subido` (si la tienda no contesta, la próxima corrida no duplica el video). `fallo`
  lleva la primera línea del error (≤ 300, sin la llave). `CupoAgotado` (subiendo o al leer el
  canal) → `cupo` a esa y para. `SinAutorizacion` tras reservar → `cupo` (vuelve a pendiente sin
  gastar intento) y sube: es de la PC, no de la máquina. Sale con 2 si alguna falló; el cupo
  agotado no es falla. Reporte: subidas, ya estaban, saltadas, fallidas, cuántas quedan (otro
  GET con límite 20: «20 o más») y cuántas esperan el clic de Mario por ser privadas.
- **Tarea diaria** (`publicacion/tarea_cola.py`): `schtasks /Create /SC DAILY /TN "Apolo - cola
  de YouTube" /TR "<pythonw> -B <publicar.py> youtube --cola --registro [--tienda/--limite/
  --publico]" /ST HH:MM /F` (sin `/RU`: corre como el usuario con su sesión abierta). El
  `pythonw.exe` del venv del checkout (sin ventana a las 02:30; si no hay, el de este proceso).
  `/TR` de más de 261 caracteres (tope de schtasks) se rechaza al instalar. `--registro` manda la
  salida a `logs/cola-youtube.log` (pasado 1 MB, el anterior queda en `.1`) y no abre el
  navegador: sin permiso guardado falla y pide `publicar youtube --cola --ensayo` una vez a mano
  (el ensayo lista la cola y el canal sin reservar, y autoriza). Al instalar avisa si
  `APOLO_TIENDA_LLAVE` no está en las variables de USUARIO (`HKCU\Environment`; «sólo en esta
  consola» si está en `$env:`) o si falta el permiso de YouTube. En no-Windows, mensaje con
  cron/systemd.
- Tests: `tests/test_publicar_cola.py` (tienda falsa con la cola, reserva 409, PUT y los
  archivos públicos; Google falso de `test_publicar_youtube.py`, que ahora reinicia lo recibido
  en cada sesión de subida y toma el total del largo declarado) y
  `tests/test_publicar_fabrica.py` (pasos falsos, ficha y tienda reales; corte y reanudación,
  ficha en rojo, candado ocupado/vencido/muerto/con espera, borrador, `--desde`, CLI).
- **Sin verificar de verdad**: la tarea registrada en el Programador de tareas (que lea la
  variable de usuario y corra con `pythonw`), la cola contra la tienda real y su R2 (URLs
  absolutas de otro origen, sin Bearer) y el cupo real de YouTube. Lo verifica F4.

### D10 — ajustes de Mario tras el primer video real (2026-10-21)

- **Sin «En cifras» en el video** (salía al final con textos cortados: «cajas de cartón y…»,
  «2 000 × 742 × 77…»; nadie lo lee ahí y la tienda ya muestra esos datos). `linea_tiempo.tramos`
  no tiene la parte `cifras` y `duracion_total` no la cuenta: VTK y navegador dejan de mostrarla
  sin tocar `ui/` (el navegador pide sólo las tarjetas del plan). `Tiempos.cifras_s` se fue: con
  el mismo objetivo, esos 6 s pasan a las etapas. `composicion.tarjeta_cifras` se borró y
  `tarjetas` da 404 a `cifras`. El guion SIGUE llevando `cifras.items` (de ahí salen las de
  `ficha.json` y del LEEME); el nuevo escribe `duracion_s: 0` y la de un guion de antes se ignora
  (ya no es error «dura más de 0 s pero no tiene cifras»). Los capítulos ya cerraban en «La
  máquina terminada»: sin cambios.
- **El cierre es la portada de la tienda** (`media/cierre.py`, fuera de `composicion.py`, que
  quedaba en 500): el hero de apolocad.com en modo oscuro (tokens de `marca-oscuro` de la tienda:
  lienzo `#0f151b` con su rejilla técnica apagada hacia los bordes), la A de taller (dibujada con
  la geometría del maestro SVG, que un test compara: `docs/` no viaja en PyPI), el lema en blanco
  y negrita en ≤ 3 líneas parejas (la letra más grande con la que entra entero), el subrayado de
  `TituloDeLaPortada.js` (la misma curva, acento `#5b8cff`, 104 % de la última línea), el dominio
  en ámbar `#f0b43c` y al pie, chico, el aviso de D8 («…no fue construido ni probado
  físicamente.»). Dura lo de siempre (5 s, con el fundido cruzado de entrada y a negro).
- **Textos** (`cierre.textos_cierre`): lema = `cierre.texto` del guion (el nuevo lo escribe:
  `APOLO_TIENDA_LEMA` o «Máquinas listas para fabricar», el `tienda.lema` de la tienda); vacío o
  el de antes («Descarga los planos y el modelo 3D») → el lema por defecto, así un guion viejo
  sale con la portada nueva. Dominio = host de `cierre.url` (la página de la máquina) sin `www.`;
  sin URL, el de `APOLO_TIENDA_URL` o apolocad.com. La miniatura no cambia.
- Tests: `tests/test_media_cierre.py` (textos, maqueta sin cortes ni solapes en 1920×1080 y
  1280×720 con lema y dominio largos, colores, la A contra el maestro, VTK = navegador, sin
  tarjeta de cifras, guion viejo válido sin cifras en el video, capítulos); ajustes en
  `test_construccion`, `test_publicacion_paquete`, `test_video_navegador`,
  `test_publicacion_ficha_auto`, `test_media_composicion` y `test_publicar_youtube` (sólo el
  título de un capítulo de ejemplo). Sin goldens tocados.
/^>>>>>>> 78aa9c2/d
### Ajuste D10 — la máquina andando con producto (2026-10-21, implementado con tests)

Mario: «una faja moviéndose sin cajas no parece que se mueva». La fábrica ya no graba la marcha
sólo cuando alguien pasa `--marcha`: con `--render navegador` la decide sola.

- **Qué marcha** (`publicacion/marcha.py`): `marcha.json` de la carpeta de la versión o, si no,
  de la del slug (el escenario de `simulate` tal cual, `{"escenario", "duracion_s"}`, o `false`
  = sin marcha); si no hay archivo, la AUTOMÁTICA de un transportador
  (`services/marcha_ejemplo.py`). Antes de ponerla en el guion la simula en proceso sobre la
  copia del documento (prepare + simulate de la dinámica, lo mismo que el navegador pide a la
  API al grabar); si falla o, en la automática, ninguna caja avanza 200 mm, el video sale sin
  marcha y lo avisa. Nunca para la fábrica. `--sin-marcha` la apaga; con `--render vtk` no se
  arma (VTK no la anima).
- **La automática** reutiliza la detección de la dinámica: la banda de `create_belt_conveyor`
  (`detectar_bandas`, con su junta virtual) y la hecha a mano con rol «Banda» si hay UNA junta
  de giro «motriz» (o una sola de giro), declarada en `bandas`; el tramo superior sale de
  `superficie_banda`. Sentido: de la cola al tambor motriz. Producto: `largo/ancho/alto_paquete_mm`
  y dos claves nuevas de los requisitos, `peso_paquete_kg` (UNA caja: `carga_kg` es la carga de
  diseño, no se usa) y `paquetes_por_minuto`; lo que falte, caja de 300 × 300 × 200 mm y 5 kg, y
  0,3 m/s sin `velocidad_m_s` (avisado como «asumido»). El ancho se recorta al 90 % de la banda.
  Cajas repartidas sobre el 55 % de la banda desde el primer cuadro (el movimiento se lee de
  entrada) + alimentación en serie por la cola, al paso que deja ~4,5 cajas a la vista (≤ 1,5 m).
- **Cuánto dura**: la parte del video = lo que tarda la caja más adelantada en caer por la
  descarga + 2 s, entre 8 y 20 s (crece con el largo, baja con la velocidad); la simulación dura
  además lo que el video sigue en 3D (cifras + órbita del guion: la marcha sigue andando), ≤ 60 s.
- **El guion**: si la fábrica lo escribe, `flujo.guion` recibe la marcha como función del
  documento y la descuenta de la duración objetivo; si el modelador ya lo dejó sin marcha, la
  fábrica abre el proyecto, la elige y la SUMA a `guion.json` (el video crece esos segundos). Un
  guion con marcha o de diseño no se toca. `estado.json` anota `marcha_s` y el reporte dice «N s
  andando» o «sin la máquina andando».
- **Medido** (laptop, en proceso sobre copias de la base): proyecto 73 (banda a mano, `j_eje_motriz`
  a 0,35 m/s, cajas 600 × 400 de los requisitos) → 8 s de marcha, 22 s simulados en ~7–10 s, 11
  cajas; proyecto 32 (dos `create_belt_conveyor`, sin requisitos) → 20 s, 34 s simulados en ~10 s.
  Cuadros con el GIF de la dinámica (VTK): las cajas viajan sobre la banda y caen por la cabeza.
  Sin marcha y avisados: 38 (banda a mano sin junta de giro) y los de rodillos 74/79/80
  (`create_roller_conveyor` no declara juntas: nada gira). **Pendiente**: la marcha automática de
  un transportador de rodillos pide juntas en sus rodillos (o que la dinámica las derive de la
  plantilla, como la junta virtual de la faja): es un cambio de `physics/`, fuera de este ajuste.
- Brief del modelador (repo privado): declarar el producto de ejemplo en los requisitos al cerrar y,
  si la máquina no es un transportador, escribir `marcha.json` probado con `simulate`.
- Tests: `tests/test_fabrica_marcha.py` (automática real sobre una `create_belt_conveyor`, con y
  sin requisitos, recorte de ancho, duración por largo y velocidad, sin banda, banda a mano sin
  junta, simulación que no avanza; `marcha.json` de la versión y del slug, `false`, roto; falla de
  armar o de simular; el paso guion con guion nuevo, existente, con marcha, de diseño, vtk y
  `--sin-marcha`; reporte).
- Sin verificar: el video real en el navegador con la marcha automática (lo verá F4).
