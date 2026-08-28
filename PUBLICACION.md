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
diario.

¿Y si la cola se vacía? Ahí entra la **generación autónoma** (sección más
abajo): un segundo cron a las 7:00 comprueba la cola y, solo si está vacía,
arranca Claude Code en modo headless en el propio VPS para generar el post
del día completo (palabras, portada, caption) y encolarlo. Tus posts
manuales siempre tienen prioridad — el bot solo actúa de red de seguridad.

El disco del VPS no se llena: tras publicar, cada post pasa a `publicados/`
y el propio publicador lo **borra a los `dias_retencion` días** (7 por
defecto, configurable). La copia permanente es Canva: los diseños de cada
post viven en la carpeta `chinesereads-posts` y las imágenes de IA
descartadas se suben como assets a su carpeta `descartes` — el VPS solo
guarda lo transitorio.

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

## Montaje en el VPS (ya hecho el 2026-08-28)

Así quedó instalado en el servidor de chinesereads.com (Ubuntu 24.04,
`root@65.21.59.130`). Los ficheros que viven fuera de este repo (el override
de Docker y las unidades de systemd) están copiados en
[`despliegue/`](despliegue/) para poder rehacerlo sin depender del servidor.

**1. Repo del publicador** en `/root/chinesereads-publicador` (no necesita
venv ni dependencias: solo Python 3 de sistema). La cola vive en
`/root/chinesereads-publicador/cola`, fuera del repo de la web.

**2. Servir la cola por HTTPS sin tocar la web.** La web va en Docker con
Caddy en contenedor, y su `Caddyfile` está versionado en el repo de la web
(`codeurjc-students/2025-ChineseTexts`), así que editarlo rompería los
`git pull` del despliegue. En vez de eso se añadió un
`docker-compose.override.yml` — fichero **nuevo y sin versionar**, que
Docker Compose fusiona solo y que sobrevive a los despliegues — montando la
cola dentro del `/srv` que Caddy ya sirve:

```yaml
# /root/2025-ChineseTexts/docker/docker-compose.override.yml
services:
  caddy:
    volumes:
      - /root/chinesereads-publicador/cola:/srv/cola-chinesereads:ro
```

Para aplicarlo (lo mismo que hace `deploy.sh` de rutina, ~2 s de parpadeo):

```bash
cd /root/2025-ChineseTexts/docker
docker compose --env-file .env up -d --force-recreate --no-deps caddy
```

→ `base_url_publica = https://chinesereads.com/cola-chinesereads`
(verificado: sirve los JPEG con `Content-Type: image/jpeg`).

**3. Config**: `/root/chinesereads-publicador/publicacion_config.json`,
`chmod 600`, con `vps.ssh` vacío (este ES el VPS). Comprobar con
`python3 publicador.py estado`.

**4. Disparo diario con systemd, no con cron.** El cron de Debian/Ubuntu
**no** entiende `CRON_TZ` (eso es de cronie/RedHat) y el servidor va en UTC:
con cron, el horario de verano movería la hora dos veces al año. systemd sí
admite zona horaria, y además no toca el crontab existente (donde vive el
backup diario de la base de datos de la web):

```ini
# /etc/systemd/system/chinesereads-publicador.timer
[Timer]
OnCalendar=*-*-* 08:00:00 Europe/Madrid
Persistent=true
RandomizedDelaySec=300
```

```bash
systemctl daemon-reload
systemctl enable --now chinesereads-publicador.timer
systemctl list-timers chinesereads-publicador.timer   # ver próximo disparo
journalctl -u chinesereads-publicador.service -n 30   # ver qué pasó
systemctl start chinesereads-publicador.service       # publicar ahora mismo
```

El servicio (`chinesereads-publicador.service`) es un `oneshot` que ejecuta
`publicador.py publicar` en el directorio del repo. Mientras no haya tokens
configurados, termina con código 1 y el log dice "No hay ninguna red
configurada" — es lo esperado, no un fallo del montaje.

## Generación autónoma: el temporizador "te llama" a Claude

Tu pregunta exacta era: *"¿yo no te llamo, sino que el cronjob te activa
automáticamente?"* — sí, exactamente así, con **Claude Code en modo
headless** (`claude -p "..."`): la misma herramienta que usas en el Mac,
instalada en el VPS, disparada por un temporizador sin interfaz. El guion
`generacion_autonoma.sh` comprueba la cola y, solo si está vacía, lanza
Claude con el encargo de `PROMPT_AUTONOMO.md`: elegir un tema variado
(consultando el historial para no repetir mundos), generar el post completo
con la skill de siempre —validaciones en código incluidas—, y encolarlo.

`PROMPT_AUTONOMO.md` codifica también tu política de contenido: temas
rotando entre mundos distintos (comida, viajes, familia, números, clima,
compras, emociones...) y, **muy de vez en cuando** (como mucho 1 de cada
8-10 posts, y solo si no hay otro reciente), un post con ángulo de
tendencia buscado en internet, tipo "5 words to text your boyfriend in
Chinese" — siempre brand-safe: sin política, polémicas ni marcas.

Montaje en el VPS (una vez, además del apartado anterior; paso a paso
detallado en [despliegue/README.md](despliegue/README.md), Parte 4):

```bash
# Claude Code necesita Node 18+ (el servidor ya tiene Node 20)
npm install -g @anthropic-ai/claude-code

# Credenciales propias para el servidor: o tu suscripción (token OAuth de
# ~1 año, imprime una URL que abres en el Mac) o una ANTHROPIC_API_KEY de
# console.anthropic.com si prefieres pago por uso aparte.
claude setup-token

# El entorno del generador: venv del servidor local + clave de Pollinations
cd /ruta/al/repo
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
# copia .pollinations_token desde el Mac (scp) — jamás por git

# El MCP de Canva necesita su OAuth UNA vez, con navegador. Desde tu Mac:
ssh -L 8090:localhost:8090 usuario@tu-vps   # (el puerto exacto lo dice el flujo)
#   → en esa sesión: cd /ruta/al/repo && claude   → /mcp → conectar canva
#   → el enlace OAuth se abre en el navegador del Mac gracias al túnel
chmod +x generacion_autonoma.sh
```

Y su temporizador, gemelo del de publicación pero una hora antes:

```ini
# /etc/systemd/system/chinesereads-generador.timer
[Timer]
OnCalendar=*-*-* 07:00:00 Europe/Madrid
Persistent=true
```

(el `.service` correspondiente ejecuta `/root/chinesereads-publicador/generacion_autonoma.sh`).
Es opcional: sin él, el sistema publica solo lo que generes tú — modo cola
pura, que es como conviene empezar.

Dos cosas que debes saber y aceptar del modo autónomo:

- Corre con `--dangerously-skip-permissions` (en headless no hay nadie que
  apruebe cada paso). Por eso: **usuario Linux propio sin privilegios**,
  que solo tenga este repo. Así el radio de acción queda acotado.
- Un post autónomo se publica **sin que un humano lo revise antes**. Las
  reglas duras (validación de longitudes, licencias, cooldowns) van en
  código y no dependen del modelo, pero un desliz estético es posible.
  Mitigación ya incluida: tus posts manuales tienen prioridad (el bot solo
  actúa con la cola vacía) y la orden es "todo o nada" — ante cualquier
  fallo a medias, aborta y ese día no se publica, que es mejor que
  publicar algo roto.

## ¿Chocará con mi web en producción?

No, y este es el porqué punto por punto:

- **Puertos**: el publicador y el generador no abren ninguno — solo hacen
  peticiones salientes (Meta, TikTok, Canva, Pollinations). Tu web sigue
  siendo la única dueña del 80/443.
- **Servidor web**: lo único que se añade es servir la carpeta `cola/`
  bajo `https://chinesereads.com/cola-chinesereads/` (symlink o `alias`).
  Es una ruta nueva que no existía: no puede pisar nada de la web actual.
- **Ficheros**: el repo vive en su propio directorio (p. ej.
  `~/mcp-server-chinesereads-canva`), sin tocar el de la web.
- **Disco**: acotado por diseño — la cola son unos pocos posts (~20 MB
  cada uno) y `publicados/` se autolimpia a los 7 días.
- **CPU/RAM**: el publicador es despreciable. La generación autónoma
  (Node + Claude) sí consume durante unos minutos al día a las 7:00 —
  en un VPS pequeño se nota como un pico breve, no como carga sostenida.
  Si tu VPS va muy justo, mueve la generación a una hora valle.
- **Cron**: entradas nuevas en tu crontab; las existentes no se tocan.

## ¿Y Metricool?

Lo investigué porque lo tienes: su API (plan Advanced, ~54 €/mes) está
pensada para leer analíticas, **no para publicar programáticamente**, así
que como motor de este sistema no sirve y las APIs oficiales gratuitas que
ya usamos son objetivamente mejores. Donde sí brilla: Metricool es partner
auditado de TikTok, así que publicar TikToks **públicos** a través de su
web funciona desde el día uno. Úsalo como puente manual para TikTok
mientras tu app pasa el audit (arrastras los PNG de `posts/` al calendario
de Metricool), y déjalo luego para lo que es bueno: mirar analíticas de
ambas cuentas en un solo sitio.

## Los pasos que te tocan a ti, en orden

Cada paso deja algo funcionando por sí mismo; puedes parar donde quieras.

1. **Instagram profesional**: cuenta `chinesereads` → Ajustes → cambiar a
   cuenta Creator (2 min, gratis).
2. **App de Meta**: developers.facebook.com → crear app → producto
   Instagram → conectar tu cuenta → generar token (sección Instagram de
   arriba). Me pasas user_id y token y monto la config contigo.
3. **VPS parte 1 (publicación)**: clonar repo, symlink de `cola/`,
   `publicacion_config.json`, probar `estado` y `--dry-run`, cron de las
   8:00. → Desde aquí, Instagram ya se publica solo desde la cola.
4. **TikTok**: app en developers.tiktok.com + verificar dominio
   chinesereads.com + OAuth → primero en `SELF_ONLY`, y pedir el audit.
   Mientras llega: TikTok a mano vía Metricool si quieres.
5. **VPS parte 2 (generación autónoma)**: Node + Claude Code +
   `setup-token` + venv + OAuth de Canva por túnel ssh + cron de las 7:00.
   → Desde aquí, el sistema entero funciona sin tu ordenador.

Para los pasos 2 y 4 (los paneles de Meta y TikTok), hazlos conmigo en una
sesión: me vas diciendo qué ves y te digo qué tocar, y verifico cada token
en el momento.

Primera prueba de fuego recomendada: un post de la cola con la cuenta de
Instagram **en privado** y TikTok en `SELF_ONLY` — se ve el resultado real
sin publicar nada al mundo. Luego, cuenta pública y a correr.

## Cómo se encola un post desde el Mac

Lo hace Claude al final del flujo de `generar-post` (paso 10 de SKILL.md):
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

### Formato de las imágenes (importante)

**Instagram solo admite JPEG** ("JPEG is the only image format supported") y
**TikTok admite JPEG/WebP, máximo 1080p y 20 MB por imagen**. Canva exporta
PNG de 2048 px, que las dos rechazarían — por eso el paso 10 del flujo llama
antes a `preparar_para_cola`, que deja en `<carpeta del post>/_cola/` los
JPEG a 1080 px que sí se publican (los PNG originales se quedan como
archivo local). Lo que se sube a la cola es siempre esa carpeta `_cola/`.

Como red de seguridad, `publicador.py` comprueba cada imagen encolada
(extensión, cabecera real del fichero y tamaño) antes de llamar a ninguna
API: si algo no es JPEG de verdad, no publica y lo dice en el log.

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
