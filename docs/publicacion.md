# Cómo funciona la publicación automática

La arquitectura y las decisiones de fondo. El montaje del servidor está en
[despliegue.md](despliegue.md); las credenciales, en
[configuracion.md](configuracion.md); cada red en
[instagram.md](instagram.md) y [tiktok.md](tiktok.md).

---

## La arquitectura en una frase

**Cola + temporizadores.** Cuando generas un post, además de descargarse
las imágenes se escribe un `meta.json` con la descripción y los hashtags ya
decididos, y la carpeta viaja por `rsync` a una cola en el servidor. Cada
día a las **20:00** (hora española) se ejecuta `publicador.py publicar`, que
coge el post **más antiguo** de la cola, lo publica en Instagram y TikTok
con las APIs oficiales, y lo archiva.

Esto **no va por MCP**, y la distinción importa: MCP es la interfaz entre un
modelo y sus herramientas, y en el servidor no hay ningún modelo corriendo
cuando se publica — solo un script de Python sin dependencias que ejecuta
decisiones ya tomadas. La parte "inteligente" (elegir palabras, redactar la
caption) ocurre al generar el post; el servidor solo aprieta el botón.

Consecuencia del modelo de cola: **el post de mañana se genera hoy**. Si
mantienes 3-5 posts en la cola, puedes estar una semana sin encender el
ordenador y la cuenta sigue publicando a diario.

¿Y si la cola se vacía? A las **19:00** se ejecuta `generacion_autonoma.sh`,
que comprueba la cola y **solo si está vacía** arranca Claude Code en el
propio servidor para generar el post del día y encolarlo. Tus posts siempre
tienen prioridad: si generaste algo, el bot ni se despierta.

## Por qué systemd y no cron

El cron de Debian/Ubuntu **ignora `CRON_TZ`** (esa variable es de cronie, el
cron de RedHat) y el servidor va en UTC: con cron, "las 20:00" se
desplazarían una hora dos veces al año con el cambio de horario. systemd sí
entiende `OnCalendar=*-*-* 20:00:00 Europe/Madrid`. Ventaja extra: no toca
el `crontab` existente, donde vive el backup diario de la base de datos de
la web.

## El disco no se llena

Tras publicarse, cada post pasa a `publicados/` y el propio publicador lo
**borra a los `dias_retencion` días** (7 por defecto). En el servidor
también poda los PNG que deja la generación autónoma en `posts/` — pero
nunca en tu Mac, donde esa carpeta es tu archivo (lo distingue por si
`vps.ssh` está relleno).

La copia permanente es **Canva**: los diseños de cada post viven en la
carpeta `chinesereads-posts` y las imágenes de IA descartadas se suben como
assets a su carpeta `descartes`. El servidor solo guarda lo transitorio.

## El formato de las imágenes (importante)

**Instagram solo admite JPEG** — su documentación es literal: *"JPEG is the
only image format supported"*. **TikTok admite JPEG o WebP, máximo 1080p y
20 MB por imagen.** Canva exporta PNG de 2048 px, que las dos rechazarían.

Por eso el flujo llama a `preparar_para_cola`, que deja en
`<carpeta del post>/_cola/` los JPEG a 1080 px que sí se publican (los PNG
originales se quedan como archivo local). Un post entero pasa de 23 MB a
1,6 MB, lo que además acelera la descarga por parte de Meta y TikTok, que
tienen tiempo de espera.

Como red de seguridad, `publicador.py` comprueba cada imagen encolada
—extensión, cabecera real del fichero y tamaño— antes de llamar a ninguna
API: si algo no es JPEG de verdad, no publica y lo dice en el log.

## Formato de `meta.json`

Va dentro de la carpeta `_cola/` que se sube:

```json
{
  "tema": "transporte público",
  "titulo": "6 words for getting around China",
  "caption": "Texto de la descripción, sin hashtags...",
  "hashtags": ["#learnchinese", "..."],
  "imagenes": ["00-portada.jpg", "01-slide.jpg", "...", "99-final.jpg"],
  "creado": "2026-08-28",
  "no_publicar_antes_de": null
}
```

- `hashtags` es opcional: sin él se usan los `hashtags_por_defecto`.
- `imagenes` fija el orden (sin él, alfabético — la portada `00-` queda
  primera igualmente y `99-final` la última).
- `no_publicar_antes_de` retiene el post hasta una fecha (`YYYY-MM-DD`).
  Útil para revisar con calma antes de que salga.

## No hay borradores

La API de Instagram no crea borradores: lo que está en la cola se publica
tal cual. Por eso el flujo termina **enseñándote las imágenes y la caption**
al encolar, y por eso existe `no_publicar_antes_de`. Los diseños siguen en
Canva y puedes editarlos y reexportar hasta el momento de la publicación.

## ¿Publicar por API reduce el alcance? ¿Shadowban?

**No, si es por la API oficial** — que es exactamente lo que hace esto.

- Meta documenta las señales de ranking de Instagram (interés, relación,
  novedad, formato...) y **el método de publicación no está entre ellas**.
  Todas las herramientas serias (Later, Buffer, Hootsuite, Metricool)
  publican por esta misma API.
- El único experimento controlado conocido (Hootsuite, en su propia cuenta)
  dio a los posts programados un engagement ligeramente **mayor** que a los
  manuales, probablemente porque programar permite elegir mejor la hora.
- El shadowban real existe, pero viene de otra cosa: bots de crecimiento a
  los que das tu contraseña, follow/unfollow masivo, hashtags baneados,
  spam repetitivo. Nada de eso aplica aquí.
- Lo que **sí** pierdes al automatizar es estar presente el primer cuarto
  de hora para responder comentarios, y la interacción temprana ayuda.
  Solución: el post sale a las 20:00; pásate un rato después a contestar.
- En TikTok igual: la API es oficial y su control es previo (la auditoría),
  no un castigo posterior al alcance.

## Límites que nos afectan

| | Instagram | TikTok |
|---|---|---|
| Imágenes por carrusel | 10 | 35 |
| Formato | JPEG | JPEG / WebP |
| Resolución | — | máx. 1080p |
| Peso | — | máx. 20 MB por imagen |
| Publicaciones al día | 100 por API | ~15 por cuenta |

Un post típico (portada + 6 palabras + slide final) son 8 imágenes: cabe de
sobra. Si algún día se pasara de 10, el publicador publica las primeras y lo
avisa en el log.

## Comandos del publicador

```bash
python3 publicador.py estado       # config, tokens y cola
python3 publicador.py cola         # posts pendientes
python3 publicador.py pendientes   # solo el número (lo usa el generador)
python3 publicador.py publicar             # publica el más antiguo
python3 publicador.py publicar --dry-run   # simula: caption, URLs, accesibilidad
python3 publicador.py publicar --solo instagram   # (o --solo tiktok)
```

Si una red falla y la otra no, el post se queda en la cola y al día
siguiente **solo se reintenta la que falló** — no se duplica la publicada.
Pero una red que falla siempre no puede bloquear la cola eternamente: tras
**3 intentos** se da por perdida, se anota en el log y el post se archiva
igualmente para dejar paso a los siguientes.

Si sabes que una red no va a funcionar durante un tiempo, mejor **pausarla**
que dejarla fallar: pon `"pausada": true` en su sección de
`publicacion_config.json` y el publicador la ignora por completo. Es lo que
está hecho ahora mismo con TikTok, a la espera de la auditoría.
