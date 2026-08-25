---
name: generar-post
description: Crear un post (carrusel) de Instagram o TikTok de N slides a partir de una plantilla propia de Canva, cambiando solo los textos (y, si la plantilla lo pide, una imagen libre de derechos). Úsala cuando el usuario pida un post, una publicación, un carrusel o contenido nuevo sobre un tema concreto, o mencione una de sus plantillas. También cuando pida "otro igual pero de X".
---

# Generar un post de N slides desde plantilla

Flujo de ocho pasos. No te saltes la validación ni el registro.

## 1. Elegir plantilla y determinar N

Si el usuario no dice cuál plantilla, llama a `listar_plantillas` y elige por la
descripción. Si dos encajan, pregunta en vez de adivinar.

El número de slides (N) lo dice el usuario en la propia petición ("5 palabras",
"6 redes sociales..."). Si no da un número explícito, pregúntaselo — no lo
inventes. N no puede superar el `max_paginas` de la plantilla (`preparar_encargo`
lo rechazará si te pasas, pero avisa antes si ya sabes que N es demasiado alto).

## 2. Pedir el contrato

Llama a `preparar_encargo(plantilla_id, tema, numero_slides)`. Te devuelve los
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
licencia `cc0` o `pdm` (dominio público). Si no hay ningún resultado con esa
licencia, no sigas con esa imagen: para y pide al usuario que la ponga él a
mano en esa slide después. Nunca uses una imagen de licencia distinta, aunque
el resultado parezca perfecto — es la regla que evita problemas legales.

## 4. Validar

Llama a `validar_contenido(plantilla_id, contenido)` con el contenido de texto de
**cada slide por separado** (no hace falta pasar los huecos de imagen). Si
`valido` es `false`, corrige lo que diga `errores` y vuelve a validar. **No
pases al paso 5 sin que las N slides estén en verde.** Reformula en vez de
truncar a lo bruto.

## 5. Crear el diseño en Canva

Con las herramientas del servidor MCP de Canva:

1. **Duplica** el diseño maestro: `copy-design(design_id=canva_design_id,
   page_numbers=[1..N])`. Esto crea un diseño nuevo de exactamente N páginas, ya
   independiente del maestro.
2. Por cada una de las N páginas: `start-editing-transaction` sobre el diseño
   nuevo, localiza los elementos de esa página cuyo texto actual coincide con el
   `texto_actual` de cada hueco, y sustitúyelos con `perform-editing-operations`
   (`replace_text` para huecos de texto). Para un hueco de imagen: sube la
   imagen encontrada con `upload-asset-from-url` y sustitúyela con `update_fill`
   sobre el elemento de imagen de esa página.
3. `commit-editing-transaction` cuando todas las páginas estén editadas.

Trabaja solo con elementos que ya están en la plantilla y con recursos
gratuitos. No añadas elementos premium: salen con marca de agua en cuentas
gratuitas.

**Regla que no se rompe nunca: no edites el diseño maestro** (`canva_design_id`
del catálogo). Todo el trabajo va sobre el diseño copiado en el paso 1.

## 6. Exportar

Llama a `get-export-formats` sobre el diseño copiado y luego `export-design`
(con `pages` cubriendo todas las N páginas) para conseguir un único link de
descarga con el post completo.

## 7. Registrar

Llama una sola vez a `registrar_publicacion(plantilla_id, tema, slides, url_diseno)`
con `slides` siendo la lista de las N slides (`identificador` + `contenido` de
cada una) y `url_diseno` el link real del paso 6. Solo después de que el diseño
exista. Esto es lo que evita repetir palabras y temas en el futuro.

## 8. Al terminar

Resume en pocas líneas: qué plantilla usaste, el tema, cuántas slides y el
enlace de descarga. Recuerda al usuario que revise el diseño antes de
publicar — la sustitución de texto puede descuadrar un salto de línea, y eso se
ve a simple vista pero el modelo no lo ve. Si alguna slide llevaba imagen
buscada automáticamente, señálalo explícitamente: la licencia está garantizada,
pero el acierto temático de la imagen conviene revisarlo a ojo.

La publicación en Instagram y TikTok es manual: exporta desde Canva y súbelo tú.
