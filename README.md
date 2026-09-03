# Generador de posts desde plantillas de Canva

Pides *"5 palabras en chino sobre deportes"* y sale un carrusel nuevo de 5
slides en tu cuenta de Canva, con la plantilla intacta y sin repetir palabras
recientes.

Y no se queda ahí: el post se publica solo en Instagram a las 20:00 (TikTok
está preparado pero en pausa: TikTok no aprueba apps de uso propio; ver
[docs/tiktok.md](docs/tiktok.md)).

Coste: **0 €**. Canva Free + el servidor MCP oficial de Canva + este servidor
local. Sin redimensionado, sin autofill de Enterprise, sin recursos premium.

## Documentación

| | |
|---|---|
| [docs/local.md](docs/local.md) | Instalar y usarlo en tu Mac |
| [docs/despliegue.md](docs/despliegue.md) | Montar el servidor desde cero |
| [docs/configuracion.md](docs/configuracion.md) | Todos los secretos: qué, de dónde y dónde va |
| [docs/instagram.md](docs/instagram.md) · [docs/tiktok.md](docs/tiktok.md) | Cada red: conexión, autenticación y estado |
| [docs/publicacion.md](docs/publicacion.md) | Cómo funciona la publicación automática |
| [docs/pollinations.md](docs/pollinations.md) | Imágenes con IA y su coste |
| [.claude/skills/generar-post/SKILL.md](.claude/skills/generar-post/SKILL.md) | El flujo de once pasos que genera un post |

Índice completo en [docs/](docs/).

## Cómo está montado

Dos servidores MCP repartiéndose el trabajo:

| Servidor | Quién lo mantiene | Qué hace |
|---|---|---|
| `canva` | Canva (remoto, OAuth) | Duplicar, leer, editar y exportar diseños |
| `catalogo-plantillas` | Tú (local, stdio) | Catálogo, límites, validación e historial |

El de Canva sabe de diseños pero no sabe nada de tus plantillas ni de lo que ya
publicaste. Ese hueco lo llena el servidor local, y ahí es donde vive la lógica
que hace que esto sea fiable: **las reglas duras las comprueba código, no el
modelo.** Contar caracteres es justo el tipo de cosa que un LLM hace regular.

El repo está partido por responsabilidades:

```
plantillas.json                      catálogo: ids de Canva, huecos, reglas, ángulos, paleta
catalogo/servidor_catalogo.py        servidor MCP local: validación, rotaciones, imágenes IA
publicacion/publicador.py            publica la cola en Instagram y TikTok (solo stdlib)
generacion/                          generación autónoma en el servidor (script + encargo)
.claude/skills/generar-post/SKILL.md el flujo de once pasos que sigue Claude
despliegue/                          deploy.sh, verificar.sh, unidades de systemd, plantillas
docs/                                toda la documentación
```

Lo que no va a git vive en la raíz: `historial.json` (memoria
anti-repetición), `publicacion_config.json` y `.pollinations_token`
(credenciales), `cola/`, `publicados/` y `posts/` (imágenes).

## Instalación

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
# Los dos servidores MCP ya vienen declarados en .mcp.json: al abrir el
# proyecto, Claude Code pide aprobarlos. Luego `/mcp` para autenticar Canva.
claude
```

Se abre el OAuth de Canva en el navegador; no hay que crear ninguna app. El
servidor local ya está declarado en `.mcp.json`, así que Claude Code lo
levanta solo al abrir el proyecto: comprueba con `/mcp` que aparecen los dos.

Paso a paso completo (config, ssh al servidor, cómo pedir un post) en
[docs/local.md](docs/local.md). Para montar el servidor:
[docs/despliegue.md](docs/despliegue.md).

## Configurar tus plantillas

Cada plantilla debe ser un diseño **multi-página** en Canva: varias páginas
duplicadas con el mismo layout. Un post de N slides se genera copiando N de
esas páginas, así que necesitas al menos tantas páginas en el maestro como
slides vayas a pedir nunca en un post.

Edita `plantillas.json` (o pide al asistente que use `anadir_plantilla`). Por cada
plantilla necesitas:

- **`canva_design_id`** — está en la URL del diseño maestro:
  `canva.com/design/DAFxxxxxxxx/edit` → el `DAFxxxxxxxx`.
- **`max_paginas`** — el máximo de slides de un post con esta plantilla.
  **8**, aunque el maestro tenga más páginas: Instagram admite 10 imágenes
  por carrusel y portada + cierre se llevan dos; con más, el publicador
  recorta en silencio.
- **`min_paginas`** — el mínimo (4 por defecto): por debajo, el post se lee en
  dos segundos y no compensa el scroll. Entre esos dos números rota
  `planificar_post`.
- **`huecos`** — un objeto por cada bloque que quieras cambiar en cada página.
  El campo `texto_actual` debe ser **literalmente** lo que pone hoy ese bloque
  en la plantilla: así es como se localiza al editar. Los de texto llevan
  `"tipo": "texto"` y `max_caracteres`; un hueco de imagen lleva
  `"tipo": "imagen"` (sin `max_caracteres`) y se rellena buscando una foto de
  licencia libre (CC0/dominio público) o, si no se encuentra ninguna, a mano.
- **`max_caracteres`** — mídelo escribiendo texto en una página hasta que se
  descuadre, y resta un par de caracteres.
- **`reglas_estilo`** — el estilo de tu contenido en frases imperativas. Esto es
  lo que más se nota en la calidad del resultado; merece la pena afinarlo.

Un consejo: nombra las plantillas de forma descriptiva en Canva
(`PLANTILLA_chino_5palabras_feed`). Ayuda a que se elija la correcta.

## Uso

En Claude Code, dentro de la carpeta del proyecto:

```
> hazme un post de 5 palabras en chino sobre deportes
```

La skill `generar-post` (`.claude/skills/generar-post/SKILL.md`) se dispara
sola. El flujo es: elegir plantilla y número
de slides → pedir el contrato de huecos → generar contenido por slide →
validar → duplicar N páginas y editarlas en Canva → exportar y descargar todas
las páginas → portada → slide final de cierre → registrar el post completo en
el historial → encolarlo para la publicación automática.

Si el contenido no pasa la validación, se corrige y se revalida antes de tocar
nada en Canva. Esa es la parte que evita que acabes con diseños rotos.

### Dónde quedan los posts generados

Canva no empaqueta un PNG multi-página en un solo archivo: el export de un
diseño de N páginas da una URL por página. El servidor las descarga todas a
`posts/<tema>[-<plantilla>]-<fecha>/` dentro del repo. Esa carpeta está en
`.gitignore` (son imágenes regenerables, no hace falta llevarlas en git) —
haz tu propia copia de seguridad si quieres conservarlas fuera del disco.

Dentro de Canva, los diseños de cada post (slides + portada) tampoco quedan
sueltos: se mueven a una carpeta propia `<tema>-<fecha>` dentro de la
carpeta madre `chinesereads-posts`, con el mismo nombre que la carpeta
local de descargas.

Las imágenes de IA candidatas que no acaban en la portada se conservan en
`posts/descartes/` — ya están generadas (y pagadas en pollen), así que se
quedan para ti en vez de borrarse.

## Portada

Cada post lleva una portada: una foto llamativa de fondo con el título del
post encima ("5 words you must know if you go to China") y la marca de agua
de la cuenta. Es un diseño **aparte** (plantilla `portada` del catálogo, de una
sola página), pero su PNG se descarga como `00-portada.png` en la misma
carpeta del post — si el experimento no convence, se quita el paso y nada más
cambia.

La foto de fondo sale de uno de estos dos sitios:

- **IA gratuita** — Pollinations.ai, vía la herramienta `generar_imagen_ia`
  del servidor local: consulta el catálogo de modelos en vivo, elige el mejor
  oficial (klein > zimage > flux, elegido comparando resultados a ojo; los
  "community" de terceros se excluyen siempre), descarga la imagen y el
  asistente la **mira** antes de usarla, regenerando con otra semilla si
  sale mal. Con la clave de la cuenta (ver abajo) usa la plataforma actual,
  que cobra en "pollen" (~0.002-0.005 por imagen: el saldo inicial de una
  cuenta nueva da para cientos); sin clave o sin saldo, cae solo al endpoint
  clásico anónimo (modelo pequeño, 768×768) en vez de fallar. Paisajes y
  primeros planos salen bien; escenas con personas, regular.
- **Tu galería** — fotos tuyas de China subidas una vez como assets de Canva.
  El asistente elige una distinta cada vez, con el mismo cooldown que las
  palabras (`portadas_recientes`), para que no se repitan seguidas.

Reglas duras en código, como siempre: hay **cinco plantillas de portada** (el
mismo diseño con el título y la marca de agua en sitios distintos, en la
carpeta de Canva `chinesereads-plantilla-portada`) y `elegir_portada` decide
cuál toca midiendo la foto, no a ojo. Calcula el contraste de cada color de
marca en la caja del título de cada variante, descarta los que no llegan a
3:1, y mide además la **marca de agua** —que va fija en rojo y no se puede
recolorear— en la caja donde caiga en cada una: elegir la variante es la
única forma de que el logo no se pierda. Entre las que aguantan la foto, gana
la que lleva más posts sin usarse; y luego el color, con el mismo criterio.
Así hay variedad en el feed sin que ningún título deje de leerse.
`portadas_recientes` es la memoria anti-repetición (fotos, colores, escenas y
variantes). La paleta se edita a mano en `plantillas.json` → plantilla
`portada` → `colores_titulo`, y las variantes en `portada.variantes`: tocar
esas listas es seguro, la legibilidad la sigue garantizando el código.

Lo mismo con el contenido: `planificar_post` decide **cuántas palabras** lleva
el post (4-8, rotando: si los últimos van todos con el mismo número,
`preparar_encargo` lo rechaza) y desde **qué ángulo** se agrupan — un campo
semántico, una categoría gramatical entera (preposiciones, adverbios de
tiempo, medidores), una situación, un ángulo de tendencia, expresiones hechas
o pares que se confunden. Los ángulos y sus pesos se editan en `plantillas.json` →
`angulos_de_post`. Es lo que evita que la cuenta acabe siendo siempre
"6 sustantivos sobre un tema".

**Mejores modelos de IA (opcional, gratis, una vez):** regístrate en
[enter.pollinations.ai](https://enter.pollinations.ai) con tu cuenta de GitHub
(OAuth solo de identidad: no da acceso a tus repos y se puede revocar en
GitHub → Settings → Applications) y crea una **API key** (`sk_...`) con solo
el permiso de modelos — sin Account Admin. Guárdala en un fichero
`.pollinations_token` en la raíz del repo:

```bash
echo "TU_CLAVE_SK" > .pollinations_token
```

Ese fichero está en `.gitignore`: no se sube a git nunca. Con la clave,
`generar_imagen_ia` usa los modelos buenos del catálogo (FLUX.2 Klein,
zimage, flux...), que cuestan "pollen" — la moneda prepago del servicio.
Precios, cómo conseguir pollen y qué pasa exactamente cuando se acaba
(spoiler: nada grave, no hay saldo negativo y el flujo no se rompe): ver
[docs/pollinations.md](docs/pollinations.md).

**Preparación (una vez):** crea en Canva un diseño de 1 página con una foto de
fondo a pantalla completa, el título de ejemplo encima, tu marca de agua de
chinesereads y —recomendado— un degradado oscuro sutil detrás de la zona del
título (hace legible cualquier foto). Regístralo con `anadir_plantilla` como
`portada`, con un hueco de texto `TITULO` y un hueco `tipo: "imagen"` para el
fondo. Si quieres usar tu galería, sube también tus fotos como assets de Canva
(arrastrar y soltar, una vez).

## Slide final

Cada post cierra con una slide fija (llamada a la acción, marca...) elegida
de la carpeta de Canva `chinesereads-plantillas-final`, que mantienes tú a
mano: sube o borra diseños `plantilla-final-N` de 1 página cuando quieras.
La carpeta se consulta en vivo en cada post y la herramienta `elegir_final`
rota en código (la que lleva más posts sin usarse); la slide elegida se
exporta tal cual —sin editarse— como `99-final.png`, la última del carrusel.
Si la carpeta está vacía, el post sale sin cierre y se avisa en el resumen.

## Cómo evita repetirse

- **Temas** (`temas_publicados`): avisa si ya publicaste un post con ese tema
  exacto (p. ej. "deportes" completo otra vez).
- **Palabras** (`elementos_usados`): las palabras usadas en los últimos
  `COOLDOWN_POSTS` posts (15 por defecto, configurable en
  `catalogo/servidor_catalogo.py`) de esa plantilla se evitan. No es un bloqueo
  permanente — pasado ese número de posts, la palabra vuelve a estar
  disponible, lo justo para que nadie la recuerde.
- **Portadas** (`portadas_recientes`): misma ventana de cooldown para la foto
  de portada (asset de galería o prompt+semilla de IA) y para no calcar la
  redacción de títulos recientes.
- **Escenas de portada** (`escenas_recientes`): un tipo de foto (callejón con
  farolillos, skyline, museo de porcelana...) no vuelve hasta pasados 30
  posts. Ventana más larga que la de las palabras, porque la portada es lo que
  se ve en la cuadrícula del perfil y es lo que más canta si se repite.
- **Variantes de portada y color del título** (`elegir_portada`): entre las
  variantes que aguantan la foto y los colores que contrastan, gana el que
  lleva más posts sin usarse.
- **Longitud y ángulo del post** (`planificar_post`): el número de slides rota
  entre 4 y 8, y si los últimos posts seguidos llevan todos el mismo,
  `preparar_encargo` lo rechaza. El ángulo (campo semántico, categoría
  gramatical, situación, tendencia, expresiones, confusiones) va por
  **cuota**: cada uno tiene un `peso` en `plantillas.json` (vocabulario 4,
  situaciones 3, expresiones 2, tendencia/gramática/confusiones 1) y gana el
  que más por debajo de su cuota va en los últimos 30 posts, sin repetir los
  3 últimos. Uniforme no valía: la cantera de vocabulario es mucho mayor que
  la de gramática, y a 1 de cada 6 la gramática se agotaba en meses.
- **Slides finales** (`elegir_final`): rotación uniforme — siempre toca la
  plantilla de cierre que lleve más posts sin usarse.

## Publicación automática (Instagram y TikTok)

Los posts no se quedan en Canva: se publican solos. `publicacion/publicador.py` (sin MCP
y sin dependencias) vive en el VPS de chinesereads.com y, cada día a las
20:00 hora española, publica el post más antiguo de la cola por las APIs
oficiales de Meta y TikTok. Un segundo temporizador a las 19:00 genera el
post del día **solo si la cola está vacía**, como red de seguridad para
cuando no enciendes el ordenador.

Montar todo esto en un servidor nuevo es un solo comando:

```bash
curl -fsSL -o deploy.sh https://raw.githubusercontent.com/josevictorgarcia/mcp-server-chinesereads-canva/main/despliegue/deploy.sh
sudo bash deploy.sh   # descárgalo antes: con `| sudo bash` la instalación se corta a la mitad
```

Documentación completa en [`docs/`](docs/) — ver el índice abajo.

## Lo que este proyecto no hace

- **No usa fotos sin licencia, nunca.** Los huecos de imagen de las slides se
  rellenan con fotos reales de licencia CC0/dominio público (Openverse); si no
  hay ninguna que encaje, segundo intento generándola con IA (Pollinations,
  gratis) y, si tampoco sale bien, se te pide a ti. Toda imagen de IA pasa un
  filtro visual antes de usarse — el servicio gratuito es irregular en calidad
  y disponibilidad, por eso nunca es la única vía.
- **No redimensiona entre formatos.** Requiere Canva Pro. Mantén una plantilla
  por formato: una de feed y otra vertical, cada una con su entrada en el
  catálogo.
- **No improvisa sin reglas.** Tanto si el post lo pides tú como si lo
  genera el cron autónomo del VPS, las reglas duras (longitudes, licencias,
  cooldowns de palabras y portadas) las comprueba código — el modo autónomo
  solo entra si la cola está vacía y aborta ante cualquier fallo a medias.
- **No sustituye la revisión.** Cambiar texto puede descuadrar un salto de
  línea, y una imagen auto-buscada puede no acertar del todo. Abre el diseño
  antes de publicar.

## Copia de seguridad: qué sobrevive a un desastre

Si el ordenador muere o borras esta carpeta, esto es lo que pasa:

- **Recuperable con `git clone`** (está todo en el repo): el código del
  servidor, `plantillas.json` (con los ids de los diseños maestros y de las
  carpetas de Canva), la skill `generar-post`, la configuración MCP (`.mcp.json`), toda la
  documentación y **el despliegue completo del servidor**
  ([`despliegue/`](despliegue/)). En el Mac: `python3 -m venv .venv &&
  ./.venv/bin/pip install -r requirements.txt` y reconectar el MCP de Canva.
  En un servidor nuevo: `deploy.sh` y la lista de
  [docs/configuracion.md](docs/configuracion.md).
- **Vive en Canva, no en tu disco**: las plantillas maestras, todos los
  diseños generados (en `chinesereads-posts/`) y los assets subidos. Los PNG
  de `posts/` se re-exportan desde ahí cuando quieras.
- **Se recrea en un minuto**: la clave de Pollinations — genera otra en
  enter.pollinations.ai y guárdala en `.pollinations_token`. Lo mismo con
  los tokens de Instagram/TikTok de `publicacion_config.json` (se regeneran
  en los paneles de Meta y TikTok), aunque una copia privada de ese fichero
  ahorra el trámite. Ojo: la copia viva del publicador es la del **VPS** —
  si muere el Mac, la publicación diaria ni se entera.
- **Lo ÚNICO que se pierde de verdad**: `historial.json` (unos KB). Los
  posts futuros seguirían funcionando, pero la memoria anti-repetición se
  vacía: podrías repetir palabras, temas o portadas sin aviso, y pierdes la
  lista de links de edición. Haz copia de este fichero de vez en cuando
  (iCloud, Drive... cualquier sitio **privado** — nunca al repo público,
  contiene links de edición). En el peor caso se puede reconstruir a mano
  mirando los diseños en Canva.

## Verificar que el servidor local funciona

```bash
./.venv/bin/python -c "
import sys; sys.path.insert(0, 'catalogo')
import servidor_catalogo as s
print(s.listar_plantillas())
print(s.preparar_encargo('texto-3', 'animales', 4))
"
```

Debe listar tus plantillas y devolver el contrato de una petición de 4 slides
para `texto-3`. Si tocas `catalogo/servidor_catalogo.py`, reconecta con
`/mcp`: el subproceso en marcha es el anterior.
