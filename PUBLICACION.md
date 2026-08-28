# Publicación automática en Instagram y TikTok

Cómo pasan los posts de la carpeta `posts/` a estar publicados solos a las
8:00 (hora española) sin encender el ordenador.

## La arquitectura en una frase

**Cola + cron.** Cuando generas un post con Claude, además de descargarse
las imágenes se escribe un `meta.json` con la descripción y los hashtags ya
decididos, y la carpeta entera se sube por `rsync` a una cola en el VPS.
Cada día a las 8:00 un cron ejecuta `publicador.py publicar`, que coge el
post **más antiguo** de la cola, lo publica en Instagram (carrusel) y TikTok
(carrusel de fotos) con las APIs oficiales, y lo archiva en `publicados/`.

Esto NO va por MCP: MCP es la interfaz entre un modelo y sus herramientas, y
en el VPS no hay ningún modelo corriendo — solo un script de Python sin
dependencias que ejecuta decisiones ya tomadas. La "inteligencia" (elegir
palabras, redactar la caption, elegir hashtags) ocurre cuando generas el
post; el VPS solo aprieta el botón.

Consecuencia importante del modelo de cola: **el post de mañana se genera
hoy** (o cualquier día antes). Si mantienes 3-5 posts en la cola, puedes
estar una semana sin tocar el ordenador y la cuenta sigue publicando a
diario. Si la cola se vacía, ese día simplemente no se publica nada (el
script lo deja anotado en `publicador.log` y no pasa nada más).

## ¿Publicar por API reduce el alcance? ¿Shadowban?

Respuesta corta: **no, si es por la API oficial** — que es exactamente lo
que hace este proyecto.

- Meta documenta las señales de ranking de Instagram (interés, relación,
  novedad, formato...) y **el método de publicación no está entre ellas**.
  Todas las herramientas serias de programación (Later, Buffer, Hootsuite,
  Metricool) publican por esta misma API, y las marcas grandes publican
  así prácticamente todo.
- El único experimento controlado conocido (Hootsuite, en su propia cuenta)
  dio a los posts programados un engagement ligeramente MAYOR que a los
  manuales — probablemente porque programar permite elegir mejor la hora.
- El shadowban real existe, pero viene de otra cosa: bots de crecimiento a
  los que das tu contraseña, follow/unfollow masivo, hashtags baneados,
  contenido repetitivo de spam. Nada de eso aplica aquí: app propia, API
  oficial, un post al día de contenido original.
- Lo que SÍ pierdes al automatizar es estar presente el primer cuarto de
  hora para contestar comentarios — la interacción temprana sí ayuda.
  Solución barata: el post sale a las 8:00; cuando te despiertes, contesta
  los comentarios desde el móvil.
- TikTok igual: la API de publicación es oficial y los posts auditados se
  tratan como cualquier otro. La protección de TikTok es previa (el audit
  de la app, ver abajo), no un castigo posterior al alcance.

## Requisitos por red (trabajo manual, una sola vez)

### Instagram

Desde finales de 2024 existe la **"Instagram API with Instagram Login"**:
ya **no hace falta página de Facebook** — basta con que la cuenta
`chinesereads` sea **profesional** (Creator o Business, se cambia gratis en
Ajustes de Instagram → Tipo de cuenta).

1. Pasa la cuenta a profesional si no lo es ya (Creator encaja mejor).
2. Entra en [developers.facebook.com](https://developers.facebook.com) con
   tu Facebook/Meta, crea una app (tipo *Business* / caso de uso Instagram)
   y añade el producto **"Instagram" → API setup with Instagram login**.
3. En ese panel, conecta tu cuenta de Instagram como cuenta de pruebas y
   **genera un token de acceso** con los permisos
   `instagram_business_basic` y `instagram_business_content_publish`.
   Para publicar en **tu propia cuenta** (con rol en la app) no hace falta
   pasar App Review ni sacar la app de modo desarrollo.
4. El panel te da también el **Instagram User ID** numérico. Copia token e
   id en `publicacion_config.json` (`instagram.user_id`,
   `instagram.access_token`).
5. El token largo dura 60 días; `publicador.py` lo renueva solo cada 7 días
   mientras el cron corra. Si el cron estuviera parado >60 días, habría que
   generar otro token en el panel (2 minutos).

Límites que nos afectan: carrusel de **máximo 10 imágenes** (un post
`texto-6` con portada son 7 — sobra; si un día hay más, el script publica
las 10 primeras y lo avisa en el log) y 100 publicaciones por API al día
(publicamos 1).

### TikTok

1. Entra en [developers.tiktok.com](https://developers.tiktok.com), crea
   una app y añade el producto **Content Posting API** con el scope
   `video.publish` (sí, también para fotos) y **Login Kit**.
2. **Verifica tu dominio** (URL prefix de `base_url_publica`) en el panel:
   TikTok solo descarga fotos con `PULL_FROM_URL` desde dominios
   verificados. Como las imágenes se sirven desde tu propio VPS, esto es
   subir un fichero de verificación a tu web y listo.
3. Autoriza tu cuenta una vez con Login Kit (flujo OAuth en el navegador)
   y guarda `client_key`, `client_secret` y el **refresh_token** en
   `publicacion_config.json`. El access token dura 24 h; el script lo
   renueva en cada ejecución con el refresh token (que dura 1 año y va
   rotando solo).
4. **El matiz importante**: una app **sin auditar** solo puede publicar en
   modo `SELF_ONLY` (solo tú ves el post; luego puedes hacerlo público a
   mano desde la app). Para publicación directa pública hay que pedir el
   **audit** de la app en el panel — es un formulario de revisión, tarda
   días/semanas y es viable para una app personal. Plan razonable: empezar
   con `SELF_ONLY` (sirve además de banco de pruebas), pedir el audit, y
   cambiar `privacy_level` a `PUBLIC_TO_EVERYONE` cuando lo aprueben.

Instagram no tiene ese matiz: público desde el primer día.

## Montaje en el VPS

```bash
# 1. Clonar el repo (el publicador no necesita venv ni dependencias)
git clone https://github.com/josevictorgarcia/mcp-server-chinesereads-canva.git
cd mcp-server-chinesereads-canva

# 2. Config real (rellenar tokens según arriba)
cp publicacion_config.ejemplo.json publicacion_config.json

# 3. Servir la cola por HTTPS (las APIs descargan las imágenes de URLs
#    públicas). Con nginx/Apache ya sirviendo tu web, basta un symlink:
mkdir -p cola
ln -s "$PWD/cola" /var/www/tu-web/cola-chinesereads
#    → base_url_publica = https://tu-dominio.com/cola-chinesereads

# 4. Probar sin publicar
python3 publicador.py estado
python3 publicador.py publicar --dry-run   # comprueba también que la URL
                                           # se ve desde fuera

# 5. Cron diario a las 8:00 hora española (crontab -e)
CRON_TZ=Europe/Madrid
0 8 * * * cd /ruta/al/repo && /usr/bin/python3 publicador.py publicar >> publicador.log 2>&1
```

Si tu cron no soporta `CRON_TZ` (los de Debian/Ubuntu sí), pon la hora en
la zona del servidor o usa un timer de systemd. El minuto exacto da igual —
"alrededor de las 8" es justo lo que queremos.

Primera prueba de fuego recomendada: un post de la cola con la cuenta de
Instagram **en privado** y TikTok en `SELF_ONLY` — se ve el resultado real
sin publicar nada al mundo. Luego, cuenta pública y a correr.

## Cómo se encola un post desde el Mac

Lo hace Claude al final del flujo de `generar-post` (paso 9 de SKILL.md):
escribe el `meta.json` (caption en inglés, hashtags — los tuyos si los das,
los de `hashtags_por_defecto` si no — y el orden de las imágenes) y sube la
carpeta con `rsync` al VPS usando `vps.ssh` y `vps.ruta_cola` de tu
`publicacion_config.json` local. Necesitas acceso ssh por clave al VPS
(`ssh-copy-id` si aún no lo tienes).

También puedes encolar a mano cualquier carpeta de `posts/`:

```bash
rsync -av posts/transporte-publico-2026-08-27/ \
  usuario@tu-vps:/ruta/repo/cola/transporte-publico-2026-08-27/
```

(siempre que dentro haya un `meta.json`; sin él, el publicador la ignora).

### Formato de `meta.json`

```json
{
  "tema": "transporte público",
  "titulo": "6 Chinese words for public transport",
  "caption": "Texto de la descripción, sin hashtags...",
  "hashtags": ["#learnchinese", "..."],
  "imagenes": ["00-portada.png", "01-slide.png", "..."],
  "creado": "2026-08-28",
  "no_publicar_antes_de": null
}
```

`hashtags` es opcional (sin él se usan los por defecto de la config);
`imagenes` fija el orden (sin él, alfabético — la portada `00-` queda
primera igualmente); `no_publicar_antes_de` permite retener un post hasta
una fecha ("YYYY-MM-DD").

## Seguridad

- `publicacion_config.json` contiene los tokens de tus cuentas: está en
  `.gitignore` y **nunca** debe acabar en el repo (que es público). En el
  VPS, `chmod 600 publicacion_config.json`.
- La cola es públicamente accesible por HTTPS (las APIs lo exigen para
  descargar las imágenes). Son imágenes que vas a publicar horas después,
  así que no es información sensible — pero no metas ahí nada que no
  quieras que se vea.
- Si un token se filtra: revoca en el panel correspondiente (Meta /
  TikTok) y genera otro. Ninguno da acceso a la contraseña de la cuenta.
