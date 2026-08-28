# Guía completa del servidor, desde cero

Todo lo que hay instalado en el VPS de chinesereads.com y cómo rehacerlo
paso a paso si un día hay que montarlo de nuevo (servidor nuevo, desastre,
o simplemente entender qué hay dónde).

Servidor actual: **Ubuntu 24.04, `root@65.21.59.130`** (Hetzner, 8 GB RAM).
Montado el 2026-08-28.

---

## Parte 0 — Mapa: qué hay y dónde

Nada de esto vive dentro de la carpeta de tu web, y nada corre como `root`.
Son tres sitios distintos, cada uno con su razón de ser:

```
/root/2025-ChineseTexts/                  ← TU WEB (repo de la universidad)
├── .git/info/exclude                     ← [MODIFICADO] +1 línea, ver abajo
└── docker/
    ├── Caddyfile                         ← INTACTO, ni se toca
    ├── docker-compose.yml                ← INTACTO, ni se toca
    └── docker-compose.override.yml       ← [NUEVO] lo único añadido aquí

/home/chinesereads/                       ← [NUEVO] usuario dedicado, sin sudo
├── publicador/                           ← este repo, clonado
│   ├── publicador.py                     (el que publica)
│   ├── publicacion_config.json           ← LOS TOKENS (chmod 600, nunca a git)
│   ├── historial.json                    ← memoria anti-repetición (chmod 600)
│   ├── .pollinations_token               ← clave de imágenes (chmod 600)
│   ├── .venv/                            (Pillow + MCP, para generar)
│   ├── generacion_autonoma.sh            (generación con Claude)
│   ├── PROMPT_AUTONOMO.md                (el encargo para Claude)
│   ├── cola/                             ← posts pendientes (servidos por HTTPS)
│   ├── publicados/                       ← publicados, se borran a los 7 días
│   └── publicador.log
├── .claude/  .claude.json                ← sesión de Claude Code del usuario
└── (su home; nada más)

/etc/
├── chinesereads-generador.env            ← [NUEVO] token de Claude (root, 600)
└── systemd/system/
    ├── chinesereads-publicador.service   ← publica (User=chinesereads)
    ├── chinesereads-publicador.timer     ← 8:00 hora española
    ├── chinesereads-generador.service    ← genera (User=chinesereads)
    └── chinesereads-generador.timer      ← 7:00 hora española
```

**Por qué un usuario dedicado y no `root`**: Claude Code **se niega a
ejecutarse como root** con permisos automáticos
(`--dangerously-skip-permissions cannot be used with root/sudo privileges`),
y con razón: un agente autónomo no debe tener el servidor entero a su
alcance. `chinesereads` no está en `sudo` y solo posee su propia carpeta, así
que el radio de acción del generador queda acotado a este proyecto. El
publicador tampoco necesita root, así que corre con el mismo usuario.

**Por qué el publicador va en `/home/chinesereads/publicador` y no dentro de
la web**: son dos proyectos independientes, con repos distintos. Mezclarlos
significaría que un `git pull` de uno pueda romper el otro. Separados, la
web no sabe que esto existe (salvo por una línea de configuración de Caddy).

**Nota sobre el fichero de entorno**: `/etc/chinesereads-generador.env` es de
`root` con permisos 600 a propósito — systemd lo lee como root *antes* de
bajar privilegios, así que el usuario `chinesereads` nunca puede leer el
token desde una shell.

**Por qué el override SÍ tiene que estar dentro de `docker/` de la web**:
Docker Compose solo carga automáticamente un `docker-compose.override.yml`
que esté **en el mismo directorio** que el `docker-compose.yml`. No hay
alternativa; a cambio, es un fichero nuevo que no modifica ninguno tuyo.

---

## Parte 1 — Montarlo desde cero en un servidor

### 1.1 Usuario dedicado y clonado del publicador

```bash
useradd -m -s /bin/bash chinesereads      # sin sudo, a propósito
chmod 755 /home/chinesereads              # para que Caddy (root) pueda leer la cola

sudo -u chinesereads git clone \
  https://github.com/josevictorgarcia/mcp-server-chinesereads-canva.git \
  /home/chinesereads/publicador
cd /home/chinesereads/publicador
sudo -u chinesereads mkdir -p cola
chmod +x generacion_autonoma.sh
```

No necesita entorno virtual ni dependencias: `publicador.py` usa solo la
biblioteca estándar de Python 3 (el sistema ya trae 3.12). El `venv` y
`requirements.txt` solo hacen falta si vas a activar la generación autónoma
(Parte 4).

### 1.2 Publicar la cola por HTTPS

Las APIs de Instagram y TikTok **no reciben ficheros**: descargan las
imágenes de una URL pública. Por eso la carpeta `cola/` tiene que ser
accesible desde internet.

Tu web va en Docker con Caddy dentro de un contenedor, y Caddy ya sirve todo
lo que encuentra en su carpeta `/srv`. Así que basta con montar la cola ahí
dentro. Crea `/root/2025-ChineseTexts/docker/docker-compose.override.yml`
(copia el de esta carpeta):

```yaml
services:
  caddy:
    volumes:
      - /home/chinesereads/publicador/cola:/srv/cola-chinesereads:ro
```

Aplícalo recreando **solo** el contenedor de Caddy (2 segundos; es lo mismo
que hace tu `deploy.sh` en cada despliegue):

```bash
cd /root/2025-ChineseTexts/docker
docker compose --env-file .env up -d --force-recreate --no-deps caddy
```

Y evita que ese fichero ensucie el git de tu web (exclusión **local**, no
versionada, no toca el `.gitignore` del repo):

```bash
echo "docker/docker-compose.override.yml" >> /root/2025-ChineseTexts/.git/info/exclude
```

Comprueba que funciona:

```bash
echo hola > /home/chinesereads/publicador/cola/prueba.txt
curl https://chinesereads.com/cola-chinesereads/prueba.txt   # → hola
rm /home/chinesereads/publicador/cola/prueba.txt
```

**Por qué NO se toca el `Caddyfile`**: está versionado en el repo de la web
(`codeurjc-students/2025-ChineseTexts`) y cada despliegue hace `git pull`.
Una edición local ahí haría fallar el pull con "your local changes would be
overwritten" y te dejaría el despliegue bloqueado.

### 1.3 Configuración con los tokens

```bash
cd /home/chinesereads/publicador
cp publicacion_config.ejemplo.json publicacion_config.json
chmod 600 publicacion_config.json      # solo root puede leerlo
nano publicacion_config.json
```

Campos importantes:

- `base_url_publica`: `https://chinesereads.com/cola-chinesereads`
- `dias_retencion`: `7` (días que se guarda un post ya publicado antes de
  borrarse del servidor; la copia permanente está en Canva)
- `vps.ssh` y `vps.ruta_cola`: **vacíos** en el servidor (este ES el VPS).
  En el Mac sí van rellenos, para que el rsync sepa a dónde subir.
- `instagram` y `tiktok`: los tokens de las Partes 2 y 3.

Este fichero es **el único que no está en GitHub**, porque contiene
credenciales. Si lo pierdes, se regenera repitiendo las Partes 2 y 3.

Comprueba:

```bash
python3 publicador.py estado
```

### 1.4 El disparo diario (systemd, no cron)

Copia `chinesereads-publicador.service` y `.timer` de esta carpeta a
`/etc/systemd/system/` y actívalos:

```bash
systemctl daemon-reload
systemctl enable --now chinesereads-publicador.timer
systemctl list-timers chinesereads-publicador.timer    # ver próximo disparo
```

**Por qué systemd y no cron**: el cron de Debian/Ubuntu **ignora `CRON_TZ`**
(esa variable es de cronie, el cron de RedHat) y este servidor va en UTC.
Con cron, "las 20:00" se desplazarían una hora dos veces al año con el
cambio de horario. systemd sí entiende `OnCalendar=*-*-* 08:00:00
Europe/Madrid`. Ventaja extra: no toca tu `crontab`, donde vive el backup
diario de la base de datos de la web.

---

## Parte 2 — La app de Instagram (Meta), paso a paso

Esto es trabajo de navegador, una sola vez. Resultado: dos datos
(`user_id` y `access_token`) que van a `publicacion_config.json`.

### 2.1 Requisitos previos

1. **Cuenta de Instagram profesional** (Creator o Business). Se cambia
   gratis en la app: Configuración → Tipo de cuenta y herramientas. Una
   cuenta personal no puede publicar por API.
2. **Un perfil de Facebook** (facebook.com). Ojo con la confusión: una
   "cuenta de Meta" con email (la de Quest/Horizon) **no sirve** —
   `developers.facebook.com` exige un perfil de Facebook. Puede ser mínimo:
   sin publicaciones, sin amigos y **sin página**. Con la API nueva
   ("Instagram API with Instagram Login") **no hace falta página de
   Facebook**, que era el requisito antiguo y el motivo por el que mucha
   documentación vieja lo pide.

### 2.2 Registrarse como desarrollador

1. Entra en **developers.facebook.com** con ese perfil de Facebook.
2. Arriba a la derecha: **"Get Started"** / "Comenzar". Aceptas los
   términos y puede pedirte verificar con móvil o tarjeta (trámite
   estándar, no cobra nada).
3. Hecho esto aparece el menú **"My Apps"** (`developers.facebook.com/apps`).
   Si no lo ves, es que el registro de desarrollador no llegó a completarse.

### 2.3 Crear la app

1. **My Apps → Create App**.
2. Nombre: `chinesereads-publisher`. Email de contacto: el tuyo.
3. Te pregunta qué quiere hacer la app ("use cases"). **Con marcar solo el
   de Instagram basta**: ese caso de uso ya trae consigo los permisos que
   necesitamos (`instagram_business_basic` e
   `instagram_business_content_publish`). No añadas Facebook Login ni
   otros: cuantos menos permisos pida la app, menos superficie expuesta y
   menos posibilidades de que Meta pida revisión. Siempre se pueden añadir
   después desde el panel si hicieran falta.
   Si esa opción no aparece, elige **"Other"** → tipo **"Business"** y
   añade el producto Instagram luego desde el menú lateral.

**Cuántas apps puedes tener**: no son infinitas, pero sobran — el límite es
de **15 apps** por cuenta de desarrollador (sin cuenta de empresa
verificada), y las archivadas también cuentan. Aquí solo necesitas una.

### 2.4 Generar el token

1. En el menú lateral de la app: **Instagram → API setup with Instagram
   login**.
2. Paso *"Generate access token"*: pulsa **Add account**, inicia sesión con
   `chinesereads` y autoriza. Los permisos que deben aparecer son
   `instagram_business_basic` e `instagram_business_content_publish`.
3. Copia el **access token** y el **Instagram User ID** numérico que muestra
   esa misma pantalla.
4. Los otros pasos de esa página (webhooks, Instagram business login) **no
   hacen falta** para publicar.

**No hace falta App Review** mientras publiques en tu propia cuenta con la
app en modo desarrollo. La revisión de Meta solo es necesaria para publicar
en cuentas de terceros.

### 2.5 Guardarlo

En `publicacion_config.json`:

```json
"instagram": {
  "user_id": "1784...",
  "access_token": "IGAA...",
  "token_refrescado": ""
}
```

El token dura **60 días**, pero `publicador.py` lo renueva solo cada 7 días
mientras el timer siga corriendo, así que en la práctica no caduca nunca. Si
el sistema estuviera parado más de 60 días, se genera otro en el panel (2
minutos).

### 2.6 Primera prueba

```bash
cd /home/chinesereads/publicador
python3 publicador.py estado                 # ¿ve la red instagram?
python3 publicador.py publicar --dry-run     # sin publicar: revisa caption y URLs
systemctl start chinesereads-publicador.service   # publicar ya, sin esperar al timer
journalctl -u chinesereads-publicador.service -n 30
```

Consejo: haz la primera con **la cuenta de Instagram en privado**. Ves el
resultado real sin que lo vea nadie, y luego la vuelves a poner pública.

---

## Parte 3 — TikTok

Más burocracia que Instagram, por eso conviene dejarlo para después de tener
Instagram funcionando.

1. **developers.tiktok.com** → crear app.
2. Añadir el producto **Content Posting API** (scope `video.publish`, que
   cubre también las fotos) y **Login Kit**.
3. **Verificar el dominio** `chinesereads.com` en el panel: TikTok solo
   descarga fotos (`PULL_FROM_URL`) desde dominios verificados. Te dará un
   fichero o un registro DNS que colocar; como las imágenes se sirven desde
   tu propio servidor, se puede hacer.
4. Autorizar tu cuenta una vez por OAuth (Login Kit) y guardar en la config
   `client_key`, `client_secret` y `refresh_token`.
5. **El matiz clave**: una app **sin auditar** solo publica en `SELF_ONLY`
   (privado, solo tú lo ves; luego puedes hacerlo público a mano en la app).
   Para publicación directa pública hay que pedir el **audit** de la app —
   formulario de revisión, tarda días o semanas. Plan sensato: empezar en
   `SELF_ONLY`, pedir el audit y, cuando lo aprueben, cambiar
   `privacy_level` a `PUBLIC_TO_EVERYONE`.

Mientras llega el audit, tu cuenta de **Metricool** sirve de puente: es
partner auditado de TikTok, así que puedes programar los TikToks públicos
arrastrando los JPEG de `_cola/`.

El access token de TikTok dura 24 h y el script lo renueva en cada ejecución
con el `refresh_token` (que dura un año y va rotando: el publicador guarda
siempre el nuevo automáticamente).

---

## Parte 4 — Claude en el servidor (generación autónoma)

Esto es **opcional**. Sin ello, el servidor publica lo que tú generes desde
el Mac; con ello, si algún día la cola está vacía a las 19:00, el propio
servidor genera el post del día.

### 4.1 ¿Hace falta una clave de Claude? Sí, una de las dos

En el servidor no hay ninguna sesión iniciada, así que Claude Code necesita
credenciales propias. Dos caminos:

| Opción | Cómo | Cuándo elegirla |
|---|---|---|
| **Tu suscripción** (recomendada) | `claude setup-token` genera un token OAuth de larga duración (≈1 año) | Ya pagas Claude; el consumo sale de tu cuota, sin factura nueva |
| **Clave de API** | Crear una en console.anthropic.com y exportar `ANTHROPIC_API_KEY` | Prefieres pago por uso separado de tu cuota personal |

No son lo mismo: el token de suscripción es "tu cuenta funcionando en el
servidor" (mismos modelos y límites que en tu Mac, sin factura aparte); la
clave de API es una **cuenta de facturación distinta**, con saldo propio y
pago por uso, que da acceso a todos los modelos de la API. Con cualquiera de
las dos, el modelo concreto se puede fijar con la variable `CLAUDE_MODELO`
en el fichero de entorno (`sonnet` abarata la generación diaria, `opus` da
la máxima calidad); sin ella se usa el modelo por defecto de Claude Code.

`claude setup-token` funciona sin navegador en el servidor: imprime una URL,
la abres en el Mac, autorizas y pegas el código de vuelta en la terminal.

El token se guarda como variable de entorno para el servicio. **No lo metas
en el repo**: ponlo en un fichero aparte solo legible por root.

```bash
# En el servidor
npm install -g @anthropic-ai/claude-code    # Node 20 ya está instalado
claude setup-token                          # sigue las instrucciones

# Guardar el token para el servicio automático
echo 'CLAUDE_CODE_OAUTH_TOKEN=el-token-que-te-dio' > /etc/chinesereads-generador.env
chmod 600 /etc/chinesereads-generador.env
```

### 4.2 El resto del entorno

```bash
cd /home/chinesereads/publicador
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt     # Pillow y el SDK de MCP
```

Copia la clave de Pollinations desde tu Mac (nunca por git):

```bash
# desde el Mac
scp .pollinations_token root@65.21.59.130:/home/chinesereads/publicador/
ssh root@65.21.59.130 'chown chinesereads: /home/chinesereads/publicador/.pollinations_token && chmod 600 /home/chinesereads/publicador/.pollinations_token'
```

El MCP de Canva necesita su OAuth **una vez, con navegador**. Desde el Mac,
abre un túnel para que el enlace de autorización pueda volver al servidor:

```bash
ssh -L 8090:localhost:8090 root@65.21.59.130
# ya dentro:
cd /home/chinesereads/publicador && claude
# → /mcp → conectar canva → se abre el enlace en el navegador del Mac
```

Los servidores MCP declarados en `.mcp.json` requieren aprobación **por
usuario y por ruta del proyecto**. Si `claude mcp list` dice *"Pending
approval"*, se aprueban desde una sesión interactiva de `claude` o, sin
interfaz, marcándolos en `~/.claude.json` del usuario:

```bash
sudo -u chinesereads python3 -c "
import json
ruta = '/home/chinesereads/.claude.json'
c = json.load(open(ruta))
p = c['projects']['/home/chinesereads/publicador']
p['enabledMcpjsonServers'] = ['catalogo-plantillas', 'canva']
p['hasTrustDialogAccepted'] = True
json.dump(c, open(ruta, 'w'), indent=2)
"
sudo -u chinesereads bash -c "cd /home/chinesereads/publicador && claude mcp list"
# los tres deben decir ✔ Connected
```

### 4.3 El historial compartido

`historial.json` (la memoria anti-repetición: palabras, temas, portadas y
slides finales ya usadas) vive en las **dos** máquinas y no está en git.
Para que ninguna de las dos repita lo que hizo la otra, el flujo de
`generar-post` lo sincroniza con `rsync -a --update` (solo sobrescribe si el
otro lado es más nuevo): lo baja del VPS antes de generar y lo sube después
de registrar. La copia inicial se hizo con:

```bash
scp historial.json root@65.21.59.130:/home/chinesereads/publicador/
ssh root@65.21.59.130 'chown chinesereads: /home/chinesereads/publicador/historial.json && chmod 600 /home/chinesereads/publicador/historial.json'
```

### 4.4 Su temporizador

Igual que el de publicación pero una hora antes, y con el fichero de
entorno. Los ficheros están en esta carpeta
(`chinesereads-generador.service` y `.timer`) → van a
`/etc/systemd/system/`:

```bash
systemctl daemon-reload
systemctl enable --now chinesereads-generador.timer   # solo cuando exista el token
```

Se instalaron ya el 2026-08-28, pero están **desactivados a propósito**
hasta que exista `/etc/chinesereads-generador.env` con las credenciales de
Claude y el MCP de Canva esté autorizado en el servidor.

`generacion_autonoma.sh` comprueba primero si hay algo en la cola: si tú ya
generaste posts, **no hace nada** (ni gasta cuota ni pollen). Solo actúa
como red de seguridad.

Dos cosas que conviene tener claras antes de activarlo: corre con
`--dangerously-skip-permissions` (en modo automático no hay nadie que
apruebe cada paso), y publica sin que un humano lo revise antes. Por eso las
reglas duras van en código y el encargo dice "todo o nada": ante cualquier
fallo, aborta y ese día no se publica.

---

## Parte 5 — Comprobaciones y averías

```bash
# ¿Cuándo se publica y qué pasó la última vez?
systemctl list-timers chinesereads-publicador.timer
journalctl -u chinesereads-publicador.service -n 50

# Estado general y cola
cd /home/chinesereads/publicador
python3 publicador.py estado
python3 publicador.py cola

# Publicar ahora mismo, sin esperar
systemctl start chinesereads-publicador.service

# ¿Sigue viva la cola pública?
docker exec docker-caddy-1 ls /srv/cola-chinesereads
curl -I https://chinesereads.com/cola-chinesereads/<carpeta>/00-portada.jpg
```

Errores típicos:

- **"No hay ninguna red configurada"** → faltan tokens en
  `publicacion_config.json`.
- **"Imágenes no publicables: ... solo admite JPEG"** → el post se encoló
  sin pasar por `preparar_para_cola`. Instagram solo acepta JPEG y TikTok
  limita a 1080p/20 MB; se regenera la carpeta `_cola/` y se vuelve a subir.
- **"Invalid OAuth access token"** → token de Instagram caducado o mal
  copiado: genera otro en el panel de Meta.
- **La cola no se ve por HTTPS** → el contenedor de Caddy perdió el
  montaje: `docker compose --env-file .env up -d --force-recreate --no-deps caddy`.

---

## Parte 6 — Desmontarlo todo

Para dejar el servidor exactamente como estaba:

```bash
systemctl disable --now chinesereads-publicador.timer
rm /etc/systemd/system/chinesereads-publicador.{service,timer}
systemctl daemon-reload

rm /root/2025-ChineseTexts/docker/docker-compose.override.yml
cd /root/2025-ChineseTexts/docker
docker compose --env-file .env up -d --force-recreate --no-deps caddy

rm -rf /home/chinesereads/publicador
```

(La línea añadida a `/root/2025-ChineseTexts/.git/info/exclude` es
inofensiva, pero puedes quitarla también.)

---

## Ficheros de referencia en esta carpeta

| Fichero | Dónde va |
|---|---|
| `docker-compose.override.yml` | `/root/2025-ChineseTexts/docker/` |
| `chinesereads-publicador.service` | `/etc/systemd/system/` |
| `chinesereads-publicador.timer` | `/etc/systemd/system/` |
| `chinesereads-generador.service` | `/etc/systemd/system/` (generación autónoma) |
| `chinesereads-generador.timer` | `/etc/systemd/system/` (generación autónoma) |

El "porqué" de cada decisión y la parte de estrategia (alcance, hashtags,
shadowban, Metricool) están en [PUBLICACION.md](../PUBLICACION.md).
