---
name: generar-post
description: Crear un post (carrusel) de Instagram o TikTok de N slides a partir de una plantilla propia de Canva, cambiando solo los textos (y, si la plantilla lo pide, una imagen libre de derechos). Úsala cuando el usuario pida un post, una publicación, un carrusel o contenido nuevo sobre un tema concreto, o mencione una de sus plantillas. También cuando pida "otro igual pero de X".
---

# Generar un post de N slides desde plantilla

Flujo de once pasos. No te saltes la validación ni el registro.

## 1. Elegir plantilla, número de slides y ángulo

**Por defecto, `texto-6`**: es la preferencia del usuario para todos los
posts. `listar_plantillas` la marca con `por_defecto: true`. Usa otra solo
si el usuario la pide por su nombre. Las que salgan con
`desactivada: true` no se pueden usar — `preparar_encargo` las rechaza.

El número de slides (N) lo dice el usuario en la propia petición ("5 palabras",
"6 redes sociales..."). **Si no lo dice, no lo inventes ni des 6 por hecho:
llama a `planificar_post`.** Devuelve dos cosas, las dos por rotación (gana la
opción que lleva más posts sin usarse):

- **`numero_slides`**: cuántas palabras lleva el post, entre `minimo` y
  `maximo` (4 a 12 en `texto-6`). Es una propuesta con fundamento, no una
  orden: si el tema da 5 palabras buenas y la sexta sería relleno, baja a 5.
  Lo que **no** puedes es repetir el número que ya llevan los últimos posts
  seguidos — `preparar_encargo` lo rechaza, y con razón: así es como acabaron
  siendo todos de 6. Ojo, un post de 10-12 slides es el doble de trabajo en
  Canva que uno de 6; si vas justo de tiempo o el servicio va lento, quédate
  en la parte baja del rango y dilo en el resumen.
- **`angulo`**: desde dónde se agrupan las palabras. No todos los posts son
  "N palabras sobre un tema" — ese es solo uno de los ángulos
  (`campo-semantico`). También valen una categoría gramatical entera
  (preposiciones, adverbios de tiempo, medidores, conectores, partículas),
  una situación concreta, un ángulo de cultura o tendencia, expresiones
  hechas, o pares que se confunden. La lista con ejemplos está en
  `plantillas.json` → `angulos_de_post`, y el ángulo elegido se registra en
  el paso 9 o la rotación no aprende.

Con el ángulo en la mano, inventa el **tema** concreto (que no esté en
`temas_publicados`). N no puede superar el `max_paginas` de la plantilla ni
bajar de `min_paginas`.

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
huecos por slide, las reglas de estilo, los temas ya publicados, los
`elementos_recientes` (palabras usadas en los últimos posts de esta plantilla,
que hay que evitar por ahora — no para siempre) y, para que veas de qué vienes,
`numeros_recientes` y `angulos_recientes`.

Si `tema_ya_usado` es `true`, avisa al usuario antes de seguir. Puede que quiera
otro tema o una segunda parte con palabras distintas.

## 3. Generar el contenido de cada slide

Para cada una de las N slides, escribe el contenido respetando las reglas de
estilo al pie de la letra. Cuenta los caracteres: los huecos tienen límites
porque el texto no cabe de otro modo y la plantilla se rompe visualmente.

- Evita repetir palabras que aparezcan en `elementos_recientes`.
- No repitas nada entre las propias slides del post: todas comparten el ángulo
  del paso 1, pero cada una es distinta.
- **Las palabras no tienen por qué ser cosas tangibles.** Un post entero de
  preposiciones y localizadores (在, 上, 里, 旁边), de adverbios de tiempo
  (已经, 马上, 刚才), de medidores (个, 只, 张, 杯), de conectores, de
  partículas modales o de verbos vale tanto como uno de comida o de familia —
  y hace falta, o la cuenta se convierte en un diccionario de sustantivos. En
  esas palabras la frase de ejemplo es lo que de verdad enseña: cuídala más
  que en las demás, y si la traducción no sale limpia, escribe la función en
  dos palabras ("at / in", "already", "measure word").
- El listón no es HSK 1-3 a rajatabla: es que el que aprende vaya a oír esa
  palabra de verdad. Si el ángulo es un drama, un meme o una muletilla, entra
  aunque no salga en ninguna lista HSK. Lo que no entra es lo rebuscado ni lo
  literario.
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
2. **Imagen de fondo** — tres orígenes, en este orden de preferencia:
   - **Descartes ya pagados**: antes de generar nada, mira qué hay en
     `posts/descartes/` (y en la carpeta `descartes` de Canva). Son imágenes
     que el usuario ya ha pagado. Si alguna encaja con el tema y no aparece en
     `portadas_recientes`, úsala: cuesta cero pollen. Y ojo a esto, porque es
     el ahorro de verdad — el color del título se cambia gratis
     (`elegir_color_titulo` + `format_text`), así que un descarte que "no
     cuadraba" en blanco puede cuadrar perfectamente en tinta o dorado. Un
     descarte reutilizado se registra igual que cualquier portada, para que el
     cooldown no lo repita al día siguiente.
   - **IA gratuita (Pollinations)**: llama a
     `generar_imagen_ia(prompt, ruta_destino=<carpeta del post>/portada-candidata.png)`
     con un prompt **escrito con guiones en vez de espacios** (una URL sin
     percent-encoding es la única que el fetcher de Canva descarga bien) y
     fotográfico **que se reconozca como China en un segundo** y a ser posible
     ligado al tema del post. Esa es la prueba que tiene que pasar la foto: si
     alguien pasando el dedo por el feed no ve "China" al instante, no vale —
     un cielo, un campo o una montaña genéricos podrían ser de cualquier
     sitio. Y el repertorio es mucho más amplio que el paisaje: ciudades y
     rascacielos, tecnología y robótica, un salón de una casa china, un bar,
     un restaurante, un plato de comida, un barrio con carteles en chino, una
     tienda, un museo, un mercado, un callejón con farolillos, un templo, un
     tren de alta velocidad, una mesa con pincel, tinta y un carácter escrito,
     el Año Nuevo chino... Los callejones con farolillos y la comida funcionan
     muy bien: úsalos sin miedo, solo no seguidos.

     **Esa lista son ejemplos, no un menú cerrado.** Es preferencia expresa
     del usuario (2026-08-31) que aparezcan temáticas y lugares que no están
     ahí: una barbería, una farmacia tradicional, una obra, un andén de
     metro, una peluquería, una lavandería, un gimnasio, una librería, una
     boda, una fábrica, un puerto, una piscina, un karaoke, una biblioteca...
     Cualquier tema o lugar corriente vale mientras se reconozca como China.
     Busca a propósito escenas que no hayas usado nunca.

     **Si el tema no tiene foto posible**, no lo fuerces. Un post de
     preposiciones, de adverbios de tiempo o de medidores no se ilustra: no
     hay foto de "已经". Tampoco es excusa para volver al paisaje de siempre.
     Coge cualquier escena que recuerde a China y que no esté en
     `escenas_recientes` —un museo, una habitación, el reloj de una estación,
     un puesto de mercado, una librería, una barbería— con su marca
     inconfundible dentro. La portada está para que se pare el dedo y para
     que se lea el título; no tiene que explicar la gramática.

     **Cooldown de escenas.** Antes de escribir el prompt, llama a
     `escenas_recientes` y elige una que NO aparezca. Repetir escena se nota
     mucho más que repetir una palabra, porque la portada es lo que se ve en
     la cuadrícula del perfil. Pueden repetirse —el usuario quiere que se
     repitan— pero pasado un tiempo prudencial: la ventana es de 30 posts, un
     mes largo de publicación diaria. Al registrar, pasa la escena en dos o
     tres palabras (`portada["escena"]`: `museo-porcelana`,
     `callejon-farolillos`, `skyline-nocturno`, `puesto-de-fruta`...); sin
     eso el cooldown no aprende.

     Pero cuidado con esa lista, porque tiene trampa: un museo, un salón o
     una tienda **genéricos** fallan la prueba igual que un cielo. Cada
     escena tiene que llevar dentro al menos una **marca inconfundible de
     China**, y hay que escribirla en el prompt: carteles y rótulos con
     caracteres chinos, tejados curvos de teja gris, columnas y farolillos
     rojos, puertas de luna, celosías de madera, cerámica azul y blanca,
     palillos y cuencos, caligrafía, tetera de barro de Yixing, hanfu, el
     perfil de Pudong... "Museo" no; "vitrinas con cerámica azul y blanca y
     cartelas en caracteres chinos" sí. "Salón" no; "salón con celosía de
     madera, tetera de barro y caligrafía enmarcada" sí. **Varía la imaginería
     respecto a `portadas_recientes`** y no repitas familia de escena dos
     posts seguidos. Paisajes, arquitectura y primeros planos sin
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

     **Claro y oscuro, a propósito**: lo que hace legible un título no es que
     la foto sea oscura, sino que la franja donde cae el texto sea
     **uniforme**. Así que pide en el prompt una zona tranquila para el
     título, pero **alterna deliberadamente el registro** entre posts: unas
     veces escena oscura (noche, interior, tormenta, azul de atardecer) y
     otras escena luminosa. Pero **luminoso no es lo mismo que gris**: una
     foto de niebla o nieve sale legible y a la vez descolorida, y en la
     cuadrícula del perfil se ve como un post en blanco y negro. Pide luz
     clara **con color**: tejados rojos bajo cielo azul, campo de té a
     mediodía, puestos de fruta con luz de día, fachadas amarillas, madera y
     textiles, farolillos sobre pared blanca. `elegir_color_titulo` lo mide y
     avisa (`casi_monocroma`); si salta y el blanco y negro no era
     deliberado, repite el prompt con más color. Mira los `color` de
     `portadas_recientes` antes de escribir el prompt: si los últimos títulos
     salieron todos claros, toca una foto luminosa, que es la que deja
     entrar el tinta y el rojo de marca. Una cuenta cuyas portadas son todas
     oscuras con letra blanca se ve monótona en la cuadrícula del perfil.

     **Frugalidad con el pollen**: cada generación nueva gasta saldo, así que
     piensa el prompt con calma ANTES de generar — incluida la composición.
     El objetivo es acertar a la primera; el tope de 3 intentos es un máximo,
     no una rutina. Y antes de gastar un intento por legibilidad, **prueba
     otro color** (paso 3): recolorear es gratis. Volver a descargar un
     prompt+seed ya generado también es gratis (caché); cambiar de semilla o
     de prompt, no.

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
3. **Variante de portada y color del título**: pasa el fichero descargado a
   `elegir_portada`. Hay **cinco** plantillas de portada (carpeta de Canva
   `chinesereads-plantilla-portada`, declaradas en `plantillas.json` →
   `portada.variantes`): el mismo diseño con el título y la marca de agua en
   sitios distintos. Cuál queda mejor no es cuestión de gusto sino de la foto,
   así que se mide:
   - mide el contraste de cada color de la paleta en la caja del título de
     cada variante (no la media de la foto entera: una foto oscura con nubes
     claras justo detrás del texto engañaba a la media);
   - y el contraste de la **marca de agua** en la caja donde caiga en esa
     variante. El logo va fijo en rojo de marca y **no se puede recolorear**:
     elegir la variante es la única palanca que hay para que no se pierda.

   Devuelve la variante (con su `canva_design_id`) y el hex del título, los dos
   ya cruzados con su rotación. Aplícalos tal cual: **ni la variante ni el
   color se eligen a ojo, ni se da el blanco por hecho**. Dos consecuencias
   prácticas:
   - Cambiar de variante y recolorear son gratis e instantáneos; regenerar la
     imagen cuesta pollen. Si el título no se lee, **prueba eso primero**.
   - Si devuelve `ninguna_viable`, esa foto no tiene salida en ninguna de las
     cinco: cambia de imagen (antes un descarte que una generación nueva).
4. **Montaje**: `copy-design` de la **variante elegida** (1 página) → muévelo
   con `move-item-to-folder` a la misma carpeta del post en Canva que el
   diseño de slides → sube la imagen (`upload-asset-from-url` con la
   `url_para_canva` que devolvió `generar_imagen_ia`, o el asset ya
   existente de galería) → `update_fill` en el hueco de imagen +
   `replace_text` del título + `format_text` con el hex del paso 3 →
   `commit`. La marca de agua de chinesereads ya vive en cada variante: no la
   toques, no la muevas y no la recolorees. Lo único que se decide sobre ella
   es en qué variante cae mejor.
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

Llama una sola vez a `registrar_publicacion(plantilla_id, tema, slides, url_diseno, portada=..., final=..., angulo=...)`
con `slides` siendo la lista de las N slides (`identificador` + `contenido` de
cada una) y `url_diseno` el link de edición del diseño en Canva (no el de
exportación). Si hubo portada, pasa
`portada={"titulo": ..., "imagen": <nombre del asset o prompt+seed>, "origen": "ia"|"galeria"|"manual", "color": <el hex aplicado>, "escena": <la escena en dos o tres palabras>, "variante": <el id que devolvió elegir_portada>}` —
sin esto el cooldown de portadas no funciona, sin `color` la rotación de
colores del título se queda parada en el mismo de siempre, sin `escena` las
portadas se repiten de tipo y sin `variante` siempre sale la misma de las
cinco plantillas. Pasa también `angulo=<el id que devolvió planificar_post>`:
es lo que impide que el siguiente post vuelva a ser del mismo corte. Para una portada de IA, `imagen`
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
   autónomo conozca lo que acabas de publicar (omítelo si estás EN el VPS:
   ahí ya es el mismo fichero). El `chmod` posterior no es opcional: el
   historial guarda enlaces de edición de Canva y solo su dueño debe poder
   leerlo. (No uses `--chmod=F600`: el rsync que trae macOS es el 2.6.9 y
   no acepta esa opción.)
   ```bash
   rsync -a --update ./historial.json <vps.ssh>:/home/chinesereads/publicador/historial.json
   ssh <vps.ssh> 'chmod 600 /home/chinesereads/publicador/historial.json'
   ```

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
