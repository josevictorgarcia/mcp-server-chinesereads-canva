---
name: generar-post
description: Crear un post (carrusel) de Instagram o TikTok de N slides a partir de una plantilla propia de Canva, cambiando solo los textos. Úsala cuando el usuario pida un post, una publicación, un carrusel o contenido nuevo sobre un tema concreto, o mencione una de sus plantillas. También cuando pida "otro igual pero de X".
---

# Generar un post de N slides desde plantilla

Flujo de once pasos. No te saltes la validación ni el registro. Todas las
rutas son relativas a la raíz del repo (donde están `plantillas.json` y
`historial.json`); las herramientas `snake_case` son del servidor MCP
`catalogo-plantillas` y las `kebab-case`, del servidor MCP de Canva.

## 1. Plantilla, número de slides y ángulo

**Plantilla: `texto-6`** salvo que el usuario pida otra por su nombre
(`listar_plantillas` la marca `por_defecto: true`; las `desactivada: true`
las rechaza `preparar_encargo`).

**Número de slides (N) y ángulo**: si el usuario da N en la petición ("5
palabras…"), úsalo. Si no, **no des 6 por hecho: llama a `planificar_post`**.
Devuelve las dos cosas por rotación (gana lo que lleva más posts sin usarse):

- `numero_slides`, entre `minimo` y `maximo` (4 a 8 en `texto-6`). Es una
  propuesta con fundamento: si el tema da 5 palabras buenas y la sexta sería
  relleno, baja a 5. Lo que no puedes es repetir el número de los últimos
  posts seguidos — `preparar_encargo` lo rechaza. El tope de 8 viene de
  Instagram (10 imágenes por carrusel, y dos se van en portada y cierre; con
  más, el publicador recorta en silencio). Un post de 8 es bastante más
  trabajo en Canva que uno de 5: si el servicio va lento, quédate abajo y
  dilo en el resumen.
- `angulo`: cómo se agrupan las palabras. "N palabras sobre un tema"
  (`campo-semantico`) es solo uno; también valen una categoría gramatical
  entera (preposiciones, adverbios de tiempo, medidores, conectores,
  partículas), una situación concreta, cultura o tendencia, expresiones
  hechas, o pares que se confunden. Lista con ejemplos en `plantillas.json`
  → `angulos_de_post`. Se registra en el paso 9 o la rotación no aprende.

Con el ángulo, inventa el **tema** concreto (que no esté en
`temas_publicados`).

## 2. Pedir el contrato

Si trabajas en el Mac (`publicacion_config.json` tiene `vps.ssh`), baja
antes el historial del servidor, por si el generador autónomo publicó algo:

```bash
rsync -a --update <vps.ssh>:/home/chinesereads/publicador/historial.json ./historial.json
```

`--update` solo sobrescribe si el del servidor es más nuevo. Si el VPS no
responde, sigue y dilo en el resumen.

Llama a `preparar_encargo(plantilla_id, tema, numero_slides)`: huecos por
slide, reglas de estilo, temas previos, `elementos_recientes` (palabras a
evitar por ahora, no para siempre), `numeros_recientes` y
`angulos_recientes`. Si `tema_ya_usado` es `true`, avisa al usuario antes de
seguir (en modo autónomo: cambia de tema).

## 3. Generar el contenido

Para cada slide, respeta las reglas de estilo al pie de la letra y cuenta
los caracteres: los límites existen porque el texto no cabe de otro modo.

- Evita `elementos_recientes` y no repitas nada entre las slides del post.
  Todas comparten el ángulo del paso 1, pero cada una es distinta.
- **Las palabras no tienen por qué ser tangibles.** Un post de preposiciones
  y localizadores (在, 上, 里, 旁边), de adverbios de tiempo (已经, 马上,
  刚才), de medidores (个, 只, 张, 杯), de conectores, de partículas o de
  verbos vale tanto como uno de comida — y hace falta, o la cuenta se
  convierte en un diccionario de sustantivos. En esas palabras la frase de
  ejemplo es lo que enseña: cuídala más, y si la traducción no sale limpia,
  escribe la función en dos palabras ("at / in", "already", "measure word").
- El listón no es HSK 1-3 a rajatabla: es que quien aprende vaya a oír esa
  palabra de verdad. Un drama, un meme o una muletilla entran aunque no
  salgan en ninguna lista HSK. Lo rebuscado y lo literario, no.
- Cada slide lleva un `identificador` (la palabra principal): es lo que se
  registra para el control de repetidos.

**Solo si la plantilla tiene un hueco `imagen`** (ninguna activa lo tiene
hoy): busca en Openverse (`https://api.openverse.org/v1/images/?q=<consulta>&license=cc0,pdm`)
filtrando **solo** licencia `cc0`/`pdm`; nunca otra licencia, por buena que
parezca. Sin resultado, segundo intento con `generar_imagen_ia` (prompt de
objeto literal, 2-3 semillas, mirando el fichero); si tampoco, para y pide
la imagen al usuario.

## 4. Validar

`validar_contenido(plantilla_id, contenido)` con el texto de **cada slide
por separado**. Si `valido` es `false`, corrige lo que diga `errores` y
revalida. **No pases al paso 5 sin las N slides en verde.** Reformula en vez
de truncar.

## 5. Crear el diseño en Canva

1. **Carpeta del post**: dentro de la carpeta madre `chinesereads-posts`
   (id en `plantillas.json` → `carpeta_posts_canva_id`; si Canva dice que
   no existe, recréala con `create-folder` en `root` y actualiza el id),
   crea una carpeta con el mismo nombre que la local:
   `<tema>[-<plantilla>]-<fecha>`. Todo diseño que crees se mueve ahí con
   `move-item-to-folder`.
2. **Duplica el maestro**: `copy-design(design_id=canva_design_id,
   page_numbers=[1..N])` → diseño nuevo de N páginas. Muévelo a la carpeta.
3. Por página: `start-editing-transaction`, localiza los elementos cuyo
   texto coincide con `texto_actual` de cada hueco y sustitúyelos con
   `perform-editing-operations` (`replace_text`). Para un hueco de imagen:
   `upload-asset-from-url` + `update_fill`.
4. `commit-editing-transaction` con todas las páginas editadas.

Solo elementos que ya están en la plantilla y recursos gratuitos (los
premium salen con marca de agua). **Nunca edites el diseño maestro**: todo
va sobre la copia del punto 2.

## 6. Exportar

`get-export-formats` y `export-design` con `pages` cubriendo las N páginas.
Canva devuelve **una URL por página**: descárgalas con `curl` a
`posts/<tema>[-<plantilla>]-<fecha>/` (carpeta en `.gitignore`).

## 7. Portada

Todo post lleva portada salvo que el usuario diga lo contrario. Es un diseño
aparte (plantilla `portada`, 1 página) cuyo PNG se guarda como
`00-portada.png` en la carpeta del post.

### 7.1 Título

En inglés, gancho corto y concreto ("5 words you must know if you go to
China", "4 food words in Chinese"). Mira `portadas_recientes` y varía la
fórmula. Valídalo con `validar_contenido('portada', {"TITULO": ...})`.

### 7.2 Foto de fondo

La foto tiene que pasar **dos pruebas**: (a) que alguien pasando el dedo por
el feed vea **China en un segundo** —un cielo, un campo, un museo o un salón
genéricos podrían ser de cualquier sitio— y (b) que **hable del post**: para
un post de ir al médico, un skyline no encaja y una farmacia sí.

- **Marca inconfundible, escrita en el prompt**: rótulos con caracteres,
  tejados curvos de teja, farolillos y columnas rojas, puertas de luna,
  celosías de madera, cerámica azul y blanca, palillos y cuencos,
  caligrafía, tetera de Yixing, hanfu, el perfil de Pudong... "Museo" no;
  "vitrinas con cerámica azul y blanca y cartelas en caracteres chinos" sí.
- **Repertorio abierto** (preferencia expresa del usuario, 2026-08-31):
  ciudades, tecnología, interiores, bares, restaurantes, comida, tiendas,
  barrios, museos, mercados, callejones con farolillos, templos, trenes,
  caligrafía, Año Nuevo... y a propósito lugares corrientes que no están en
  ninguna lista: una barbería, una farmacia tradicional, una obra, un andén
  de metro, una lavandería, un gimnasio, una librería, una boda, un puerto,
  un karaoke. Callejones y comida funcionan muy bien: sin miedo, solo no
  seguidos.
- **Tema abstracto** (preposiciones, adverbios, medidores...): no hay foto
  de "已经", no la fuerces ni vuelvas al paisaje de siempre. Cualquier
  escena que recuerde a China y no esté en `escenas_recientes` vale (un
  museo, una habitación, el reloj de una estación, una librería...): la
  portada está para que se pare el dedo y se lea el título.
- **Cooldown de escenas**: antes de escribir el prompt, `escenas_recientes`
  y elige una que no aparezca (ventana de 30 posts; repetir escena canta
  más que repetir palabra porque es lo que se ve en la cuadrícula). Al
  registrar, `portada["escena"]` en dos o tres palabras
  (`museo-porcelana`, `callejon-farolillos`, `puesto-de-fruta`).
- **Claro y oscuro, a propósito**: lo que hace legible el título es que la
  franja donde cae sea **uniforme**, no que la foto sea oscura. Pide una
  zona tranquila para el título y alterna el registro entre posts (noche,
  interior, azul de atardecer / luz de día). Pero **luminoso no es gris**:
  niebla o nieve salen legibles y descoloridas, y en el perfil parecen
  blanco y negro. Luz clara **con color**: tejados rojos bajo cielo azul,
  puestos de fruta, fachadas amarillas, madera, textiles. Mira los `color`
  de `portadas_recientes`: si los últimos títulos salieron claros, toca una
  foto luminosa (la que deja entrar tinta y rojo de marca). Paisajes,
  arquitectura y primeros planos sin gente salen mejor que escenas con
  personas. Manda la legibilidad sobre la espectacularidad.

Orígenes, en este orden:

1. **Descartes ya pagados** (`posts/descartes/` y la carpeta `descartes` de
   Canva): úsalo **solo si encaja de verdad con el tema** (prueba b) y no
   está en `portadas_recientes`. "Es de China" no basta. Si ninguno encaja,
   genera: la portada tiene que hablar del post y eso vale más que el medio
   céntimo de una imagen. Un descarte reutilizado se registra como
   cualquier portada.
2. **IA (Pollinations)**: `generar_imagen_ia(prompt, ruta_destino=<carpeta
   del post>/portada-candidata.png)` con el prompt **con guiones en vez de
   espacios** (una URL sin percent-encoding es la única que el fetcher de
   Canva descarga bien) y fotográfico. La herramienta elige el mejor modelo
   oficial (klein/zimage/flux con clave y saldo; si no, cae al clásico a
   768×768 y lo dice en `endpoint`/`avisos`) y devuelve `url_para_canva`.
   **Mira** el fichero: borrosa, deforme o pobre → otra `seed`, **3 intentos
   como tope excepcional**, no rutina: piensa el prompt (incluida la
   composición) antes de gastar. Antes de gastar un intento por
   legibilidad, prueba lo gratis: variante y color (7.3). Redescargar un
   prompt+seed ya generado es gratis (caché); cambiar de seed o prompt, no.
   No reutilices un prompt+seed de `portadas_recientes`. Si el servicio
   está caído, no insistas más de un par de minutos: galería o foto CC0 de
   Openverse, y dilo en el resumen.

   **Descartes**: las candidatas que no acaben en la portada van a
   `posts/descartes/<fecha>-<tema>-vN.jpg` y a Canva:
   `upload-asset-from-url` con su `url_para_canva` (gratis, es caché),
   nombre `descarte-<fecha>-<tema>-vN`, y `move-item-to-folder` a la
   carpeta `descartes` (`carpeta_descartes_canva_id`).
3. **Galería del usuario**: `get-assets`, elige una foto cuyo nombre/id no
   esté en `portadas_recientes` y descarga su miniatura para medirla.

### 7.3 Variante de portada y color del título

Pasa el fichero a `elegir_portada`. Hay **cinco** plantillas de portada
(carpeta de Canva `chinesereads-plantilla-portada`, declaradas en
`plantillas.json` → `portada.variantes`): el mismo diseño con el título y la
marca de agua en sitios distintos. Cuál queda mejor lo decide la foto, así
que se mide: contraste de cada color de la paleta en la caja del título de
cada variante, y contraste de la **marca de agua** —fija en rojo, **no se
puede recolorear**— en la caja donde caiga. Devuelve la variante (con su
`canva_design_id`) y el hex del título, cruzados con su rotación.
Aplícalos tal cual: **ni la variante ni el color se eligen a ojo, ni se da
el blanco por hecho.** Cambiar de variante y recolorear son gratis; si el
título no se lee, prueba eso antes de regenerar. Si devuelve
`ninguna_viable`, cambia de imagen. Si avisa `casi_monocroma` y el blanco y
negro no era deliberado, repite el prompt con más color.

### 7.4 Montaje y exportación

`copy-design` de la **variante elegida** (1 página) → `move-item-to-folder`
a la carpeta del post → `upload-asset-from-url` (la `url_para_canva`, o el
asset de galería) → en una transacción: `update_fill` del fondo,
`replace_text` del título y `format_text` con el hex → `commit`. La marca de
agua ya vive en cada variante: no se toca, no se mueve, no se recolorea.
Exporta y descarga como `00-portada.png`.

## 8. Slide final

Todo post cierra con una slide fija, de la carpeta de Canva
`chinesereads-plantillas-final` (`carpeta_finales_canva_id`), que el usuario
mantiene a mano: consúltala **en vivo**.

1. `list-folder-items` (tipo `design`). Vacía → el post va sin cierre, no
   es un error: sáltalo y dilo en el resumen.
2. `elegir_final(candidatos)` con los títulos: la rotación la decide código.
3. La elegida **no se edita ni se copia**: `export-design` directo (1
   página) → `99-final.png` en la carpeta del post (el 99 la deja siempre la
   última).
4. Guarda título e id para el registro.

## 9. Registrar

Una sola llamada, solo cuando el diseño exista de verdad:

```
registrar_publicacion(plantilla_id, tema, slides, url_diseno,
                      portada={...}, final={...}, angulo=<id de planificar_post>)
```

- `slides`: las N (`identificador` + `contenido`). `url_diseno`: el link de
  edición de Canva (no el de exportación).
- `portada`: `{"titulo", "imagen": <asset o prompt+seed+modelo>, "origen":
  "ia"|"galeria"|"manual", "color": <hex aplicado>, "escena": <dos o tres
  palabras>, "variante": <id de elegir_portada>}`.
- `final`: `{"nombre": <título de la plantilla-final>, "design_id": ...}`.

Cada campo alimenta una rotación: sin `color`, `escena`, `variante`,
`final` o `angulo`, esa rotación se queda parada y el siguiente post repite.

## 10. Encolar para publicación automática

Si existe `publicacion_config.json` en la raíz, el post se encola para que
el VPS lo publique solo (docs/publicacion.md). Si no existe, salta este paso
y dilo en el resumen.

1. **Caption**, en inglés y en la voz de la cuenta (@chinesereadsapp):
   corta y sin adornos.

   ```
   How to express surprise in chinese

   Follow for more!

   #learnchinese #chineseexpressions #dku #chineselanguage #chineselanguagelearning
   ```

   Primera línea: gancho o pregunta directa ("Have you ever mistaken
   them?", "Did you know all of them? 🤔"), que varíe el título de la
   portada sin calcarlo. Una llamada a la acción que invite a comentar o
   seguir. Cuando encaje, el plug tal cual lo escribe él: "Learn chinese
   with chinesereads.com". **Nada de listas de palabras**: el vocabulario
   ya está en las slides. **Hashtags**: si el usuario los dio, esos; si no,
   no los escribas en la caption (el publicador añade los
   `hashtags_por_defecto`) y en `hashtags` del meta.json pon una mezcla de
   esos con 2-3 del tema, **unos 5 en total**. Nada de bloques de 20.
2. **`preparar_para_cola(<carpeta del post>)`**: Instagram solo admite
   JPEG y TikTok limita a 1080p/20 MB. Deja en `<carpeta>/_cola/` los `.jpg`
   a 1080 px; los PNG originales se quedan como archivo.
3. **`meta.json`** dentro de `_cola/` (formato en docs/publicacion.md):
   `tema`, `titulo` (el de la portada), `caption` (sin hashtags),
   `hashtags` (opcional), `imagenes` (los `.jpg` en orden: portada, slides,
   `99-final.jpg`), `creado` (hoy).
4. **Subir `_cola/`** (nunca la carpeta entera):
   - `vps.ssh` relleno (Mac): `rsync -av <carpeta>/_cola/ <vps.ssh>:<vps.ruta_cola>/<nombre del post>/`.
     Si falla (VPS caído), no es un error del post: deja el comando listo y
     dilo en el resumen.
   - `vps.ssh` vacío (estás EN el VPS): copia `_cola/` a `cola/<nombre del
     post>/` y comprueba con `python3 publicacion/publicador.py cola` que
     aparece.
5. **Sube el historial** (solo desde el Mac; en el VPS ya es el mismo
   fichero). El `chmod` no es opcional: guarda enlaces de edición de Canva.
   (No uses `--chmod=F600`: el rsync 2.6.9 de macOS no lo acepta.)

   ```bash
   rsync -a --update ./historial.json <vps.ssh>:/home/chinesereads/publicador/historial.json
   ssh <vps.ssh> 'chmod 600 /home/chinesereads/publicador/historial.json'
   ```
6. **Enséñaselo al usuario**: `SendUserFile` con los `.jpg` de `_cola/`
   (portada primero) y la caption y hashtags exactos. Es su única
   oportunidad de revisarlo: la API de Instagram no crea borradores.

El post sale a las 20:00 (hora española) del primer día en que sea el más
antiguo de la cola. Para retenerlo, `no_publicar_antes_de` en el meta.json.

## 11. Al terminar

Resume en pocas líneas: plantilla, tema, N, ángulo, carpeta local y cuándo
saldrá (posición en la cola × 1 post/día a las 20:00). Recuerda que la
sustitución de texto puede descuadrar un salto de línea que tú no ves, y que
la portada de IA la filtraste tú pero la última palabra sobre si representa
a la cuenta es suya: sigue a tiempo de retocar en Canva y reexportar antes
de esa hora.
