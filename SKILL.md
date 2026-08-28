---
name: generar-post
description: Crear un post (carrusel) de Instagram o TikTok de N slides a partir de una plantilla propia de Canva, cambiando solo los textos (y, si la plantilla lo pide, una imagen libre de derechos). Úsala cuando el usuario pida un post, una publicación, un carrusel o contenido nuevo sobre un tema concreto, o mencione una de sus plantillas. También cuando pida "otro igual pero de X".
---

# Generar un post de N slides desde plantilla

Flujo de once pasos. No te saltes la validación ni el registro.

## 1. Elegir plantilla y determinar N

Si el usuario no dice cuál plantilla, llama a `listar_plantillas` y elige por la
descripción. Si dos encajan, pregunta en vez de adivinar.

El número de slides (N) lo dice el usuario en la propia petición ("5 palabras",
"6 redes sociales..."). Si no da un número explícito, pregúntaselo — no lo
inventes. N no puede superar el `max_paginas` de la plantilla (`preparar_encargo`
lo rechazará si te pasas, pero avisa antes si ya sabes que N es demasiado alto).

## 2. Pedir el contrato

**Antes de nada, si trabajas en el Mac y `publicacion_config.json` tiene
`vps.ssh`**, baja el historial del servidor por si el generador autónomo
publicó algo mientras tanto (si no, repetirías palabras o portadas):

```bash
rsync -a --update <vps.ssh>:/home/chinesereads/publicador/historial.json ./historial.json
```

`--update` solo sobrescribe si el del servidor es más nuevo, así que nunca
pierdes lo tuyo. Si el VPS no responde, sigue sin bloquearte y dilo en el
resumen final.

Luego llama a `preparar_encargo(plantilla_id, tema, numero_slides)`. Te devuelve los
huecos por slide, las reglas de estilo, los temas ya publicados y los
`elementos_recientes` (palabras usadas en los últimos posts de esta plantilla,
que hay que evitar por ahora — no para siempre).

Si `tema_ya_usado` es `true`, avisa al usuario antes de seguir. Puede que quiera
otro tema o una segunda parte con palabras distintas.

## 3. Generar el contenido de cada slide

Para cada una de las N slides, escribe el contenido respetando las reglas de
estilo al pie de la letra. Cuenta los caracteres: los huecos tienen límites
porque el texto no cabe de otro modo y la plantilla se rompe visualmente.

- Evita repetir palabras que aparezcan en `elementos_recientes`.
- No repitas nada entre las propias slides del post (todas del mismo campo
  semántico, pero cada una distinta).
- Cada slide necesita un `identificador` propio (normalmente la palabra/carácter
  principal de esa slide) — es lo que se registrará luego para el control de
  repetidos.

**Si la plantilla tiene un hueco de tipo `imagen`:** busca en la API pública de
Openverse (`https://api.openverse.org/v1/images/?q=<consulta>&license=cc0,pdm`)
una imagen que represente el significado del carácter, filtrando **solo**
licencia `cc0` o `pdm` (dominio público). Nunca uses una imagen de otra
licencia, aunque el resultado parezca perfecto — es la regla que evita
problemas legales.

Si no hay ningún resultado CC0/PDM que encaje, **segundo intento con IA**:
llama a `generar_imagen_ia(prompt, ruta_destino)` con un prompt de objeto
literal ("a bowl of white steamed rice, minimalist food photography, clean
background") y la ruta dentro de la carpeta del post. La herramienta elige el
mejor modelo disponible, descarga la imagen y devuelve `url_para_canva` para
el `upload-asset-from-url` posterior. **Mira** el fichero descargado; si tras
2-3 semillas ninguna es clara y reconocible, o el servicio no responde (se
satura a ratos), para y pide la imagen al usuario. Una imagen generada por IA
no tiene el problema de licencia, pero sí puede salir deforme — el filtro
visual no es opcional.

## 4. Validar

Llama a `validar_contenido(plantilla_id, contenido)` con el contenido de texto de
**cada slide por separado** (no hace falta pasar los huecos de imagen). Si
`valido` es `false`, corrige lo que diga `errores` y vuelve a validar. **No
pases al paso 5 sin que las N slides estén en verde.** Reformula en vez de
truncar a lo bruto.

## 5. Crear el diseño en Canva

Con las herramientas del servidor MCP de Canva:

1. **Carpeta del post en Canva**: la carpeta madre `chinesereads-posts` ya
   existe y su id está en `plantillas.json` (`carpeta_posts_canva_id`); si
   Canva dice que no existe, recréala con `create-folder` en `root` y
   actualiza ese id. Crea dentro una carpeta nueva para este post
   con el mismo nombre que la carpeta local (`<tema>[-<plantilla>]-<fecha>`).
   Todos los diseños que crees en los pasos siguientes se mueven ahí con
   `move-item-to-folder` — así cada post queda agrupado en Canva y no
   suelto en la raíz.
2. **Duplica** el diseño maestro: `copy-design(design_id=canva_design_id,
   page_numbers=[1..N])`. Esto crea un diseño nuevo de exactamente N páginas, ya
   independiente del maestro. Muévelo a la carpeta del post.
3. Por cada una de las N páginas: `start-editing-transaction` sobre el diseño
   nuevo, localiza los elementos de esa página cuyo texto actual coincide con el
   `texto_actual` de cada hueco, y sustitúyelos con `perform-editing-operations`
   (`replace_text` para huecos de texto). Para un hueco de imagen: sube la
   imagen encontrada con `upload-asset-from-url` y sustitúyela con `update_fill`
   sobre el elemento de imagen de esa página.
4. `commit-editing-transaction` cuando todas las páginas estén editadas.

Trabaja solo con elementos que ya están en la plantilla y con recursos
gratuitos. No añadas elementos premium: salen con marca de agua en cuentas
gratuitas.

**Regla que no se rompe nunca: no edites el diseño maestro** (`canva_design_id`
del catálogo). Todo el trabajo va sobre el diseño copiado en el paso 1.

## 6. Exportar

Llama a `get-export-formats` sobre el diseño copiado y luego `export-design`
(con `pages` cubriendo todas las N páginas). Canva no empaqueta un PNG
multi-página en un solo archivo: devuelve **una URL por página**. Descarga las
N con `curl` a una carpeta local `posts/<tema>[-<plantilla>]-<fecha>/` dentro
del repo (esa carpeta está en `.gitignore`, no se sube a git — son imágenes
regenerables, no código).

## 7. Portada

Todo post lleva portada salvo que el usuario diga lo contrario. Es un diseño
**independiente** (la plantilla `portada` del catálogo, de 1 página), pero su
PNG se guarda en la **misma carpeta** del post, como `00-portada.png`, para que
el post quede completo en un solo sitio. Si el catálogo aún no tiene la
plantilla `portada`, salta este paso y avísalo en el resumen final.

1. **Título**: en inglés, gancho corto tipo "5 words you must know if you go
   to China" o "4 food words in Chinese". Consulta `portadas_recientes` y varía
   la redacción respecto a los títulos recientes. Valídalo con
   `validar_contenido('portada', {"TITULO": ...})`.
2. **Imagen de fondo** — dos orígenes, por preferencia del usuario:
   - **IA gratuita (Pollinations)**: llama a
     `generar_imagen_ia(prompt, ruta_destino=<carpeta del post>/portada-candidata.png)`
     con un prompt **escrito con guiones en vez de espacios** (una URL sin
     percent-encoding es la única que el fetcher de Canva descarga bien) y
     fotográfico de estética China **ligado al tema del post**:
     comida → mercado o plato; transporte → tren, estación, bicis; naturaleza
     → paisaje... No siempre el mismo tipo de escena (los callejones con
     farolillos quedan muy bien, pero varía la imaginería respecto a
     `portadas_recientes`). Paisajes, arquitectura y primeros planos sin
     gente funcionan mejor que escenas con personas. Y manda la legibilidad:
     mejor una imagen algo menos espectacular con una zona tranquila donde
     el título respire que una espectacular que se coma las letras. La herramienta elige sola el mejor modelo oficial
     del catálogo (klein/zimage/flux si hay clave en `.pollinations_token` y
     saldo de pollen; si no, cae al clásico anónimo a 768×768 — aceptable, y
     el resultado dice en `endpoint` y `avisos` qué pasó), descarga la imagen y
     devuelve `url_para_canva` para el montaje. **Mira** el fichero (lee la
     imagen): si sale borrosa, deforme o pobre, reintenta con otra `seed`
     (hasta 3 veces; si ninguna convence, pasa a galería o pregunta). No
     reutilices un prompt+seed que aparezca en `portadas_recientes`. Ojo: el
     servicio gratuito se cae a ratos; si la herramienta falla, no insistas
     más de un par de minutos — pasa a la galería del usuario o a una foto
     CC0 de paisaje de Openverse y díselo en el resumen.

     **Frugalidad con el pollen**: cada generación nueva gasta saldo, así que
     piensa el prompt con calma ANTES de generar — incluida la composición
     (pide una zona tranquila, oscura o despejada, donde irá el título:
     regenerar por legibilidad es el error caro típico). El objetivo es
     acertar a la primera; el tope de 3 intentos es un máximo, no una
     rutina. Volver a descargar un prompt+seed ya generado es gratis
     (caché); cambiar de semilla o de prompt, no.

     **Descartes**: las candidatas que no acaben en la portada no se borran —
     muévelas a `posts/descartes/` con nombre descriptivo
     (`<fecha>-<tema>-vN.jpg`). Son del usuario y ya están pagadas. Además,
     súbelas a Canva (la copia que sobrevive aunque se limpie el disco):
     `upload-asset-from-url` con la `url_para_canva` de cada candidata
     (gratis: es caché) y nombre `descarte-<fecha>-<tema>-vN`, y mueve el
     asset con `move-item-to-folder` a la carpeta `descartes` de Canva
     (id en `plantillas.json` → `carpeta_descartes_canva_id`).
   - **Galería del usuario (assets de Canva)**: lista sus fotos subidas con
     `get-assets` y elige una cuyo nombre/id **no** esté en
     `portadas_recientes` — la rotación es lo que evita que la portada se
     repita. Descarga su miniatura para el paso de brillo.
3. **Brillo**: pasa el fichero descargado a `analizar_brillo`. Si recomienda
   título "claro" u "oscuro" distinto del color por defecto de la plantilla,
   ajústalo con `format_text` al editar. Si `contraste_justo` es `true`,
   comprueba que el degradado/sombra de la plantilla sigue detrás del título.
4. **Montaje**: `copy-design` de la plantilla `portada` (1 página) → muévelo
   con `move-item-to-folder` a la misma carpeta del post en Canva que el
   diseño de slides → sube la imagen (`upload-asset-from-url` con la
   `url_para_canva` que devolvió `generar_imagen_ia`, o el asset ya
   existente de galería) → `update_fill` en el hueco de imagen +
   `replace_text` del título → `commit`. La marca de agua de chinesereads ya
   vive en la plantilla maestra: no la toques.
5. **Exportar y descargar** como `00-portada.png` en la carpeta del post.

## 8. Slide final

Todo post cierra con una slide final (después de las de vocabulario), salvo
que no haya ninguna disponible. Las plantillas de cierre las mantiene el
usuario A MANO en la carpeta de Canva `chinesereads-plantillas-final` (id en
`plantillas.json` → `carpeta_finales_canva_id`): puede añadir, borrar o
renombrar `plantilla-final-N` cuando quiera, así que consúltala **en vivo**
en cada post:

1. `list-folder-items` sobre esa carpeta (tipo `design`). Si está vacía, el
   post va sin cierre — no es un error: salta el paso y dilo en el resumen.
2. Pasa los títulos a `elegir_final(candidatos)`. La rotación (la que lleva
   más posts sin usarse; entre nunca-usadas, al azar) la decide código — no
   elijas tú.
3. La slide elegida **no se edita ni se copia**: `export-design` directamente
   sobre ese diseño (1 página, solo lectura) y descarga el PNG como
   `99-final.png` en la carpeta del post — el 99 la deja siempre la última
   al ordenar, detrás de portada y slides.
4. Guarda título e id para el registro del paso siguiente.

## 9. Registrar

Llama una sola vez a `registrar_publicacion(plantilla_id, tema, slides, url_diseno, portada=..., final=...)`
con `slides` siendo la lista de las N slides (`identificador` + `contenido` de
cada una) y `url_diseno` el link de edición del diseño en Canva (no el de
exportación). Si hubo portada, pasa
`portada={"titulo": ..., "imagen": <nombre del asset o prompt+seed>, "origen": "ia"|"galeria"|"manual"}` —
sin esto el cooldown de portadas no funciona. Para una portada de IA, `imagen`
es el prompt+seed (y el modelo). Si hubo slide final, pasa también
`final={"nombre": <título de la plantilla-final>, "design_id": ...}` — sin
esto la rotación de `elegir_final` no aprende. Solo después de que el diseño
exista. Esto es lo que evita repetir palabras, temas, fotos de portada y
slide de cierre.

## 10. Encolar para publicación automática

Si existe `publicacion_config.json` en la raíz del repo con la sección
`vps` rellena, el post se encola para que el VPS lo publique solo (ver
docs/publicacion.md). Si el fichero no existe, salta este paso sin más y dilo en
el resumen final.

1. **Caption** (descripción de la publicación), en inglés y **en la voz de
   la cuenta** (@chinesereadsapp). Su patrón real, corto y sin adornos:

   ```
   How to express surprise in chinese

   Follow for more!

   #learnchinese #chineseexpressions #dku #chineselanguage #chineselanguagelearning
   ```

   - Primera línea: gancho corto o pregunta directa ("Have you ever
     mistaken them?", "Did you know all of them? 🤔"). Puede variar el
     título de la portada, no calcarlo.
   - Una línea de llamada a la acción que invite a comentar o seguir
     ("Let me know in the comments!", "Comment if you knew them!",
     "Follow for more!"). Los comentarios tempranos ayudan al alcance.
   - Cuando encaje, el plug de la web tal y como lo escribe él:
     "Learn chinese with chinesereads.com".
   - **Nada de listas de palabras**: sus captions son breves; el
     vocabulario ya está en las slides.
   - **Hashtags**: si el usuario dio hashtags en la petición, usa ESOS. Si
     no, no los escribas en la caption: el publicador añade los
     `hashtags_por_defecto`. En `hashtags` del meta.json puedes poner una
     mezcla de esos y 2-3 específicos del tema — **unos 5 en total**, que
     es lo que usa la cuenta. Nada de bloques de 20 hashtags.
2. **Convertir las imágenes**: llama a `preparar_para_cola(<carpeta del
   post>)`. Instagram solo admite **JPEG** y TikTok limita a 1080p y 20 MB,
   así que los PNG de 2048 px de Canva no valen para publicar: la
   herramienta deja en `<carpeta del post>/_cola/` los `.jpg` a 1080 px
   listos (los PNG originales se quedan intactos como archivo).
3. **`meta.json`** dentro de esa carpeta `_cola/`, con el formato
   documentado en docs/publicacion.md: `tema`, `titulo` (el de la portada),
   `caption` (sin hashtags), `hashtags` (opcional, ver arriba), `imagenes`
   (los **.jpg**, en orden: portada primero, luego las slides y
   `99-final.jpg` la última si la hay), `creado` (fecha de hoy).
4. **Subir a la cola** (siempre la carpeta `_cola/`, nunca la del post
   entero — los PNG no se publican y ocuparían el triple):
   - Si `vps.ssh` tiene valor (estás en el Mac): `rsync -av <carpeta del
     post>/_cola/ <vps.ssh>:<vps.ruta_cola>/<nombre del post>/`. Si el
     rsync falla (VPS caído, sin red), no es un error del post: dilo en el
     resumen y deja el comando listo para que el usuario lo lance luego.
   - Si `vps.ssh` está vacío (estás EN el VPS, modo autónomo): copia
     `_cola/` a `cola/<nombre del post>/` en la raíz del repo y comprueba
     con `python3 publicador.py cola` que aparece.

5. **Sube el historial actualizado** al servidor, para que el generador
   autónomo conozca lo que acabas de publicar:
   `rsync -a --update ./historial.json <vps.ssh>:/home/chinesereads/publicador/historial.json`
   (omítelo si estás EN el VPS: ahí ya es el mismo fichero).

6. **Enséñaselo al usuario**: manda las imágenes del post
   (`SendUserFile` con los `.jpg` de `_cola/`, portada primero) junto con la
   caption y los hashtags exactos que se publicarán. Es su única
   oportunidad de revisarlo antes de que salga solo: la API de Instagram no
   crea borradores, así que lo que hay en la cola se publica tal cual.

El post se publicará automáticamente a las 20:00 (hora española) del primer
día en que sea el más antiguo de la cola. Si el usuario quiere retenerlo
hasta una fecha, o revisarlo con calma antes, pon `no_publicar_antes_de` en
el meta.json (así se queda en la cola sin publicarse hasta esa fecha).

## 11. Al terminar

Resume en pocas líneas: qué plantilla usaste, el tema, cuántas slides y en qué
carpeta local quedaron descargadas las imágenes. Recuerda al usuario que
revise el diseño antes de publicar — la sustitución de texto puede descuadrar
un salto de línea, y eso se ve a simple vista pero el modelo no lo ve. Si
alguna slide llevaba imagen buscada automáticamente, señálalo explícitamente:
la licencia está garantizada, pero el acierto temático de la imagen conviene
revisarlo a ojo. Lo mismo con una portada generada por IA: ya la filtraste
visualmente, pero la última palabra sobre si representa bien a la cuenta es
del usuario.

Si el post quedó encolado (paso 10), di cuándo saldrá (posición en la cola ×
1 post/día a las 20:00) y recuerda que sigue a tiempo de retocarlo en Canva y
reexportar antes de esa hora. Si no hay publicación automática configurada,
la subida a Instagram y TikTok es manual.
