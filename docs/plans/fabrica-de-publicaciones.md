---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: aprobado por Mario (2026-10-21) con la cola de YouTube en la tienda (D5); F1 lanzada; faltan F0, T (pedido de la tienda tras PED-124), F2, F3 y F4
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
  de música (D9); el brief del modelador suma la sección «redacta la ficha» (D1) en
  `docs/fabrica.md`, junto con el orden de la orquestación (D7). Depende de PED-124 sólo por el
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

(vacía)
