# Montar el servidor desde cero

Cómo dejar un servidor nuevo publicando solo, empezando por una máquina
recién creada. La parte automatizable está en un script; lo demás son las
credenciales, que por definición se ponen a mano.

Servidor actual: **Ubuntu 24.04, `root@65.21.59.130`** (Hetzner, 8 GB RAM),
montado el 2026-08-28. La web `chinesereads.com` vive en esa misma máquina,
en Docker.

---

## El camino corto

```bash
curl -fsSL https://raw.githubusercontent.com/josevictorgarcia/mcp-server-chinesereads-canva/main/despliegue/deploy.sh | sudo bash
```

Eso deja el sistema montado y te dice por pantalla qué credenciales faltan.
Luego sigues [configuracion.md](configuracion.md) y ya está.

El script es **idempotente**: se puede repetir sin romper nada — no
sobrescribe configuraciones existentes, y si el repo ya está clonado hace
`git pull` en vez de fallar. Probado en un contenedor Ubuntu limpio.

Variables que admite, por si el servidor nuevo no es igual:

| Variable | Por defecto | Para qué |
|---|---|---|
| `CHINESEREADS_USER` | `chinesereads` | Usuario sin privilegios que ejecuta todo |
| `CHINESEREADS_REPO` | este repo en GitHub | Por si trabajas sobre un fork |
| `CHINESEREADS_WEB_DOCKER` | `/root/2025-ChineseTexts/docker` | Dónde está el `docker-compose.yml` de la web. Vacío = no publicar la cola desde aquí |

## Qué hace exactamente el script

**1. Crea el usuario sin privilegios.** Todo corre como `chinesereads`, que
no está en `sudo`. No es una manía: Claude Code **se niega a ejecutarse como
root** con permisos automáticos (*"--dangerously-skip-permissions cannot be
used with root/sudo privileges"*), y con razón — un agente autónomo no debe
tener el servidor entero a su alcance. El publicador tampoco necesita root.

**2. Clona el repo y prepara Python.** `publicador.py` funciona con el
Python del sistema sin dependencias; el `.venv` (Pillow + MCP) solo hace
falta para la generación autónoma.

**3. Publica la cola por HTTPS.** Instagram y TikTok no reciben ficheros:
**descargan** las imágenes de una URL pública. Como la web va en Docker con
Caddy en contenedor, y Caddy ya sirve todo lo que hay en su `/srv`, basta
con montar ahí la carpeta de la cola:

```yaml
# docker-compose.override.yml (fichero NUEVO, sin versionar)
services:
  caddy:
    volumes:
      - /home/chinesereads/publicador/cola:/srv/cola-chinesereads:ro
```

Esto merece una explicación, porque es la decisión más delicada del
montaje. El `Caddyfile` de la web **está versionado** en el repo
`codeurjc-students/2025-ChineseTexts`, y su despliegue hace `git pull`:
editarlo dejaría el despliegue bloqueado con un *"your local changes would
be overwritten"*. En cambio, Docker Compose fusiona automáticamente
cualquier `docker-compose.override.yml` que encuentre junto al
`docker-compose.yml`, así que **añadimos un fichero nuevo sin tocar ninguno
existente**, y sobrevive a los despliegues. El script lo añade además a
`.git/info/exclude` (exclusión local, no versionada) para que ni aparezca
en `git status` ni se cuele en un `git add -A`.

Aplicarlo recrea solo el contenedor de Caddy: ~2 segundos, lo mismo que
hace el `deploy.sh` de la web de rutina.

Resultado: `https://chinesereads.com/cola-chinesereads/` sirve la cola en
solo lectura. **Si tu servidor nuevo no tiene esa web**, el script lo avisa
y tendrás que publicar la carpeta de otro modo (cualquier servidor web
apuntando a `cola/` sirve) y ajustar `base_url_publica`.

**4. Instala los temporizadores** de systemd: publicar a las 20:00 y
generar a las 19:00, hora española. El de generación queda desactivado
hasta que exista el token de Claude, para no llenar el journal de errores.

**5. Deja las plantillas de configuración** y explica qué falta.

## Actualizar un servidor que ya funciona

El mismo script sirve: **vuelve a ejecutarlo**. Hace `git pull`,
resincroniza las unidades de systemd y el override de Docker, reinstala las
dependencias y no toca nada que ya esté bien — en particular, **no recrea
Caddy si el montaje no ha cambiado**, así que tu web ni se entera.

```bash
sudo bash /home/chinesereads/publicador/despliegue/deploy.sh
```

Si el cambio es solo de código o documentación, basta con un `git pull` como
el usuario del servicio. El script es la opción segura cuando no estás
seguro de qué cambió.

Para comprobar en cualquier momento que el servidor coincide exactamente con
el repositorio:

```bash
sudo bash /home/chinesereads/publicador/despliegue/verificar.sh
```

Compara el commit y el estado del repo, las cuatro unidades de systemd y el
override de Docker contra sus copias versionadas, revisa que los secretos
estén presentes con permisos 600 y fuera de git, comprueba que no se haya
colado nada sensible en la carpeta pública, y termina con el estado de los
temporizadores. No modifica nada: solo informa.

## Lo que el script NO puede hacer

Las credenciales. Todas están en [configuracion.md](configuracion.md):
tokens de Instagram y TikTok, clave de Pollinations, token de Claude y el
OAuth del MCP de Canva. Y `historial.json`, que no es un secreto pero es
irreemplazable: tráetelo de la máquina anterior.

## Mapa: qué queda dónde

Estructura real del servidor. Los ficheros marcados con 🔒 son secretos con
permisos 600; los marcados con 🌐 son lo único accesible desde internet.

```
/root/2025-ChineseTexts/                   ← LA WEB (repo ajeno, no se toca)
├── .git/info/exclude                      ← +1 línea (exclusión local)
└── docker/
    ├── Caddyfile                          ← INTACTO
    ├── docker-compose.yml                 ← INTACTO
    └── docker-compose.override.yml        ← NUEVO: publica la cola

/home/chinesereads/                        ← usuario dedicado, sin sudo
├── .claude/  .claude.json                 ← sesión de Claude Code (MCP, OAuth de Canva)
└── publicador/                            ← este repo, clonado
    │
    ├── publicador.py                      ← publica (Python de sistema, sin dependencias)
    ├── servidor_catalogo.py               ← servidor MCP local (catálogo, validación)
    ├── generacion_autonoma.sh             ← genera con Claude si la cola está vacía
    ├── plantillas.json                    ← catálogo: ids de Canva, huecos, reglas
    ├── SKILL.md  PROMPT_AUTONOMO.md       ← el flujo y el encargo autónomo
    ├── .mcp.json  requirements.txt
    ├── README.md
    │
    ├── 🔒 publicacion_config.json         ← tokens de Instagram y TikTok
    ├── 🔒 .pollinations_token             ← clave de generación de imágenes
    ├── 🔒 historial.json                  ← memoria anti-repetición (irreemplazable)
    │
    ├── 🌐 cola/                           ← posts pendientes: LO ÚNICO público
    ├── publicados/                        ← ya publicados, se borran a los 7 días
    ├── posts/                             ← PNG de la generación autónoma (se podan)
    ├── publicador.log
    │
    ├── docs/                              ← toda la documentación
    ├── despliegue/                        ← deploy.sh, verificar.sh, unidades, plantillas
    └── .venv/                             ← Pillow + MCP (76 MB, solo para generar)

/etc/
├── 🔒 chinesereads-generador.env          ← token de Claude (de root, no del usuario)
└── systemd/system/
    ├── chinesereads-publicador.{service,timer}   ← 20:00 hora española
    └── chinesereads-generador.{service,timer}    ← 19:00 hora española
```

Lo importante de este dibujo: **los tres secretos del proyecto están un
nivel por encima de `cola/`**, que es la única carpeta montada en Caddy. Para
el servidor web, la carpeta madre sencillamente no existe — por eso pedir
`chinesereads.com/publicacion_config.json` devuelve la portada de la web y
no el fichero. El cuarto secreto, el token de Claude, vive en `/etc` y es de
`root`: systemd lo lee antes de bajar privilegios, así que ni el usuario del
proyecto puede leerlo desde una shell.

## Generación autónoma (opcional)

Es la única pieza que publica sin que un humano lo haya visto antes, así
que conviene activarla cuando lleves unas semanas viendo que todo va fino.

```bash
npm install -g @anthropic-ai/claude-code     # necesita Node 18+
claude setup-token                           # ver configuracion.md
```

Además: el `.venv` (ya lo crea el script), la clave de Pollinations, el
OAuth de Canva y `historial.json`. Todo detallado en
[configuracion.md](configuracion.md).

El OAuth de Canva **debe hacerse con el usuario del servicio**: copiar las
credenciales de otro usuario caduca a las pocas horas y deja la generación
autónoma muerta sin avisar. Si el generador termina sin encolar nada,
lo primero que hay que mirar es `claude mcp list` con ese usuario.

El historial vive en las **dos** máquinas, así que el flujo de
`generar-post` lo sincroniza con `rsync -a --update` (solo gana el más
nuevo): lo baja del servidor antes de generar y lo sube después de
registrar. Sin eso, el generador del servidor repetiría palabras o portadas
tuyas.

Dos cosas que aceptas al activarla: corre con
`--dangerously-skip-permissions` (en automático no hay nadie que apruebe
cada paso, de ahí el usuario sin privilegios), y publica sin revisión
previa. Mitigaciones ya incluidas: solo actúa con la cola vacía, las reglas
duras están en código, y el encargo es "todo o nada" — ante cualquier fallo
aborta y ese día no se publica.

## Comprobaciones y averías

```bash
systemctl list-timers 'chinesereads-*'                # próximos disparos
journalctl -u chinesereads-publicador.service -n 50   # qué pasó
systemctl start chinesereads-publicador.service       # publicar ahora
sudo -u chinesereads python3 /home/chinesereads/publicador/publicador.py estado
docker exec docker-caddy-1 ls /srv/cola-chinesereads  # ¿montaje vivo?
```

| Síntoma | Causa y solución |
|---|---|
| `No hay ninguna red configurada` | Faltan tokens en `publicacion_config.json` |
| `Imágenes no publicables: ... solo admite JPEG` | El post se encoló sin pasar por `preparar_para_cola` |
| `Invalid OAuth access token` | Token de Instagram caducado: genera otro en el panel de Meta |
| La cola no se ve por HTTPS | Caddy perdió el montaje: `docker compose --env-file .env up -d --force-recreate --no-deps caddy` |
| El generador no arranca | Falta `/etc/chinesereads-generador.env` o el timer está desactivado |

## Desmontarlo todo

Para dejar el servidor exactamente como estaba:

```bash
systemctl disable --now chinesereads-publicador.timer chinesereads-generador.timer
rm /etc/systemd/system/chinesereads-*.{service,timer}
systemctl daemon-reload
rm /etc/chinesereads-generador.env

rm /root/2025-ChineseTexts/docker/docker-compose.override.yml
cd /root/2025-ChineseTexts/docker
docker compose --env-file .env up -d --force-recreate --no-deps caddy

userdel -r chinesereads
```

## Ficheros de referencia

En [`despliegue/`](../despliegue/) están las copias de todo lo que vive
fuera de este repo en el servidor:

| Fichero | Dónde va |
|---|---|
| `deploy.sh` | se ejecuta, no se copia (instala **y** actualiza) |
| `verificar.sh` | se ejecuta: comprueba que el servidor coincide con el repo |
| `docker-compose.override.yml` | `/root/2025-ChineseTexts/docker/` |
| `chinesereads-publicador.{service,timer}` | `/etc/systemd/system/` |
| `chinesereads-generador.{service,timer}` | `/etc/systemd/system/` |
| `chinesereads-generador.env.ejemplo` | `/etc/chinesereads-generador.env` (rellenar) |
| `tiktok-callback.html` | `cola/`, solo durante el OAuth de TikTok |
