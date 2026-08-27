# Generador de posts desde plantillas de Canva

Pides *"5 palabras en chino sobre deportes"* y sale un carrusel nuevo de 5
slides en tu cuenta de Canva, con la plantilla intacta y sin repetir palabras
recientes.

Coste: **0 €**. Canva Free + el servidor MCP oficial de Canva + este servidor
local. Sin redimensionado, sin autofill de Enterprise, sin recursos premium.

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

## Instalación

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Conecta Canva desde Claude (Ajustes → Conectores → Canva) o, en Claude Code:

```bash
claude mcp add --transport http canva https://mcp.canva.com/mcp
```

Se abre el OAuth de Canva en el navegador. No hay que crear ninguna app ni
gestionar API keys.

El servidor local ya está declarado en `.mcp.json`, así que Claude Code lo
levanta solo al abrir el proyecto. Comprueba con `/mcp` que aparecen los dos.

## Configurar tus plantillas

Cada plantilla debe ser un diseño **multi-página** en Canva: varias páginas
duplicadas con el mismo layout (hasta el número que pongas en `max_paginas`,
p. ej. 12). Un post de N slides se genera copiando N de esas páginas, así que
necesitas al menos tantas páginas en el maestro como slides vayas a pedir
nunca en un post.

Edita `plantillas.json` (o pide al asistente que use `anadir_plantilla`). Por cada
plantilla necesitas:

- **`canva_design_id`** — está en la URL del diseño maestro:
  `canva.com/design/DAFxxxxxxxx/edit` → el `DAFxxxxxxxx`.
- **`max_paginas`** — cuántas páginas tiene el maestro (= el máximo de slides
  que podrá tener un post con esta plantilla).
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

La skill `generar-post` se dispara sola. El flujo es: elegir plantilla y número
de slides → pedir el contrato de huecos → generar contenido por slide →
validar → duplicar N páginas y editarlas en Canva → exportar y descargar todas
las páginas → registrar el post completo en el historial.

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

Reglas duras en código, como siempre: `analizar_brillo` mide la luminosidad de
la foto y decide si el título va claro u oscuro (nada de confiar en el ojo del
modelo), y `portadas_recientes` es la memoria anti-repetición.

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
[POLLINATIONS.md](POLLINATIONS.md).

**Preparación (una vez):** crea en Canva un diseño de 1 página con una foto de
fondo a pantalla completa, el título de ejemplo encima, tu marca de agua de
chinesereads y —recomendado— un degradado oscuro sutil detrás de la zona del
título (hace legible cualquier foto). Regístralo con `anadir_plantilla` como
`portada`, con un hueco de texto `TITULO` y un hueco `tipo: "imagen"` para el
fondo. Si quieres usar tu galería, sube también tus fotos como assets de Canva
(arrastrar y soltar, una vez).

## Cómo evita repetirse

- **Temas** (`temas_publicados`): avisa si ya publicaste un post con ese tema
  exacto (p. ej. "deportes" completo otra vez).
- **Palabras** (`elementos_usados`): las palabras usadas en los últimos
  `COOLDOWN_POSTS` posts (15 por defecto, configurable en
  `servidor_catalogo.py`) de esa plantilla se evitan. No es un bloqueo
  permanente — pasado ese número de posts, la palabra vuelve a estar
  disponible, lo justo para que nadie la recuerde.
- **Portadas** (`portadas_recientes`): misma ventana de cooldown para la foto
  de portada (asset de galería o prompt+semilla de IA) y para no calcar la
  redacción de títulos recientes.

## Lo que este proyecto no hace

- **No publica en Instagram ni TikTok.** El MCP de Canva llega hasta exportar a
  imagen o PDF. Publicar es otra integración (APIs de Meta y TikTok) y no es
  gratis en tiempo de montaje.
- **No usa fotos sin licencia, nunca.** Los huecos de imagen de las slides se
  rellenan con fotos reales de licencia CC0/dominio público (Openverse); si no
  hay ninguna que encaje, segundo intento generándola con IA (Pollinations,
  gratis) y, si tampoco sale bien, se te pide a ti. Toda imagen de IA pasa un
  filtro visual antes de usarse — el servicio gratuito es irregular en calidad
  y disponibilidad, por eso nunca es la única vía.
- **No redimensiona entre formatos.** Requiere Canva Pro. Mantén una plantilla
  por formato: una de feed y otra vertical, cada una con su entrada en el
  catálogo.
- **No corre solo.** El MCP responde cuando tú abres una conversación. No hay
  nada programado generando posts de madrugada.
- **No sustituye la revisión.** Cambiar texto puede descuadrar un salto de
  línea, y una imagen auto-buscada puede no acertar del todo. Abre el diseño
  antes de publicar.

## Verificar que el servidor local funciona

```bash
./.venv/bin/python -c "
import servidor_catalogo as s
print(s.listar_plantillas())
print(s.preparar_encargo('texto-3', 'animales', 4))
print(s.elementos_usados('texto-3'))
print(s.portadas_recientes())
"
```

Debe listar tus plantillas y devolver el contrato de una petición de 4 slides
para `texto-3`.
