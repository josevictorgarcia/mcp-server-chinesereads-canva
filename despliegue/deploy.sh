#!/bin/bash
# Instalación completa del publicador de chinesereads en un servidor nuevo.
#
#   curl -fsSL https://raw.githubusercontent.com/josevictorgarcia/mcp-server-chinesereads-canva/main/despliegue/deploy.sh | sudo bash
#
# o, si ya has clonado el repo:  sudo bash despliegue/deploy.sh
#
# Sirve igual para INSTALAR en un servidor nuevo y para ACTUALIZAR uno que
# ya funciona: hace git pull, resincroniza las unidades de systemd y el
# override de Docker, y no toca nada que ya esté correcto (no recrea Caddy
# si el montaje no ha cambiado, y nunca sobrescribe configuraciones).
#
# Qué hace (todo idempotente: se puede repetir sin romper nada):
#   1. Crea el usuario sin privilegios que ejecutará todo.
#   2. Clona el repo en su home y prepara el entorno de Python.
#   3. Publica la carpeta de la cola por HTTPS a través del Caddy de la web.
#   4. Instala las unidades de systemd (publicar 20:00, generar 19:00).
#   5. Deja plantillas vacías para los secretos y explica qué falta.
#
# Lo que este script NO hace, porque son credenciales y se ponen a mano
# (ver docs/configuracion.md): tokens de Instagram y TikTok, clave de
# Pollinations, token de Claude, y el OAuth del MCP de Canva.

set -euo pipefail

USUARIO="${CHINESEREADS_USER:-chinesereads}"
DESTINO="/home/${USUARIO}/publicador"
REPO="${CHINESEREADS_REPO:-https://github.com/josevictorgarcia/mcp-server-chinesereads-canva.git}"
# Directorio del docker-compose de la web (para publicar la cola por HTTPS).
# Déjalo vacío si en este servidor no está la web: la cola habrá que
# publicarla de otro modo (ver docs/despliegue.md).
WEB_DOCKER="${CHINESEREADS_WEB_DOCKER:-/root/2025-ChineseTexts/docker}"

log() { echo -e "\n\033[1m== $*\033[0m"; }

if [ "$(id -u)" -ne 0 ]; then
    echo "Ejecuta este script como root (sudo)." >&2
    exit 1
fi

# ─────────────────────────────────────────────────────────── 1. usuario
log "1/5 Usuario sin privilegios: ${USUARIO}"
if id "$USUARIO" >/dev/null 2>&1; then
    echo "   ya existe"
else
    useradd -m -s /bin/bash "$USUARIO"
    echo "   creado"
fi
# El home debe ser atravesable para que Caddy (root, en Docker) lea la cola.
chmod 755 "/home/${USUARIO}"

# ─────────────────────────────────────────────────────── 2. repo y entorno
log "2/5 Repo y entorno de Python"
apt-get update -qq
apt-get install -y -qq git python3-venv python3-full rsync sudo >/dev/null

if [ -d "${DESTINO}/.git" ]; then
    sudo -u "$USUARIO" git -C "$DESTINO" pull --quiet
    echo "   repo actualizado"
else
    sudo -u "$USUARIO" git clone --quiet "$REPO" "$DESTINO"
    echo "   repo clonado en ${DESTINO}"
fi

sudo -u "$USUARIO" mkdir -p "${DESTINO}/cola" "${DESTINO}/publicados"
chmod +x "${DESTINO}/generacion_autonoma.sh"

# El venv solo hace falta para la generación autónoma (Pillow + MCP);
# publicador.py funciona con el Python del sistema, sin dependencias.
if [ ! -x "${DESTINO}/.venv/bin/python" ]; then
    sudo -u "$USUARIO" python3 -m venv "${DESTINO}/.venv"
fi
sudo -u "$USUARIO" "${DESTINO}/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$USUARIO" "${DESTINO}/.venv/bin/pip" install --quiet -r "${DESTINO}/requirements.txt"
echo "   entorno listo"

# ──────────────────────────────────────────────── 3. cola pública por HTTPS
log "3/5 Publicar la cola por HTTPS"
if [ -n "$WEB_DOCKER" ] && [ -f "${WEB_DOCKER}/docker-compose.yml" ]; then
    # Fichero NUEVO y sin versionar: no toca ningún fichero del repo de la web
    # (en particular, jamás el Caddyfile, que se actualiza con git pull).
    NUEVO="$(sed "s#/home/chinesereads/publicador/cola#${DESTINO}/cola#" \
        "${DESTINO}/despliegue/docker-compose.override.yml")"
    ACTUAL=""
    [ -f "${WEB_DOCKER}/docker-compose.override.yml" ] && \
        ACTUAL="$(cat "${WEB_DOCKER}/docker-compose.override.yml")"

    # Que el git de la web lo ignore, sin tocar su .gitignore versionado.
    EXCLUDE="$(dirname "$WEB_DOCKER")/.git/info/exclude"
    if [ -f "$EXCLUDE" ] && ! grep -qxF "docker/docker-compose.override.yml" "$EXCLUDE"; then
        echo "docker/docker-compose.override.yml" >> "$EXCLUDE"
    fi

    if [ "$NUEVO" = "$ACTUAL" ]; then
        echo "   ya montada y sin cambios (no se toca Caddy)"
    else
        printf '%s\n' "$NUEVO" > "${WEB_DOCKER}/docker-compose.override.yml"
        ENV_ARG=""
        [ -f "${WEB_DOCKER}/.env" ] && ENV_ARG="--env-file .env"
        ( cd "$WEB_DOCKER" && docker compose $ENV_ARG up -d --force-recreate --no-deps caddy >/dev/null 2>&1 )
        echo "   montada en el Caddy de la web (recreado en ~2 s)"
    fi
else
    echo "   AVISO: no se encontró el docker-compose de la web en ${WEB_DOCKER}."
    echo "   La cola NO está publicada. Sin una URL pública, Instagram y TikTok"
    echo "   no pueden descargar las imágenes. Ver docs/despliegue.md."
fi

# ────────────────────────────────────────────────────────── 4. systemd
log "4/5 Temporizadores (publicar 20:00, generar 19:00, hora española)"
for unidad in chinesereads-publicador chinesereads-generador; do
    for ext in service timer; do
        sed -e "s#/home/chinesereads/publicador#${DESTINO}#g" \
            -e "s#^User=chinesereads#User=${USUARIO}#" \
            -e "s#^Group=chinesereads#Group=${USUARIO}#" \
            "${DESTINO}/despliegue/${unidad}.${ext}" \
            > "/etc/systemd/system/${unidad}.${ext}"
    done
done
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    systemctl daemon-reload
    systemctl enable --now chinesereads-publicador.timer >/dev/null 2>&1
    echo "   publicador activado"
    # El generador solo se activa si ya existe el token de Claude: sin él,
    # fallaría cada noche llenando el journal de errores.
    if [ -s /etc/chinesereads-generador.env ] && grep -q "^CLAUDE\|^ANTHROPIC" /etc/chinesereads-generador.env; then
        systemctl enable --now chinesereads-generador.timer >/dev/null 2>&1
        echo "   generador activado"
    else
        echo "   generador NO activado todavía (falta /etc/chinesereads-generador.env)"
    fi
else
    echo "   unidades escritas, pero este sistema no usa systemd: sin activar"
fi

# ──────────────────────────────────────────────── 5. plantillas de secretos
log "5/5 Plantillas de configuración"
CONFIG="${DESTINO}/publicacion_config.json"
if [ ! -f "$CONFIG" ]; then
    sudo -u "$USUARIO" cp "${DESTINO}/publicacion_config.ejemplo.json" "$CONFIG"
    echo "   creado publicacion_config.json a partir de la plantilla"
else
    echo "   publicacion_config.json ya existe (no se toca)"
fi
chown "${USUARIO}:${USUARIO}" "$CONFIG"
chmod 600 "$CONFIG"

if [ ! -f /etc/chinesereads-generador.env ]; then
    cp "${DESTINO}/despliegue/chinesereads-generador.env.ejemplo" /etc/chinesereads-generador.env
    chmod 600 /etc/chinesereads-generador.env
    echo "   creado /etc/chinesereads-generador.env a partir de la plantilla"
fi

cat <<FIN

════════════════════════════════════════════════════════════════════
 Instalación terminada. Falta la parte que NO puede automatizarse:
 las credenciales. Paso a paso en docs/configuracion.md

   1. Tokens de Instagram y TikTok  → ${CONFIG}   (chmod 600)
      Cómo obtenerlos: docs/instagram.md y docs/tiktok.md
   2. Clave de Pollinations         → ${DESTINO}/.pollinations_token
   3. Historial (si lo traes de otra máquina, para no repetir palabras):
      rsync tu historial.json a ${DESTINO}/historial.json
   4. Solo si quieres generación autónoma:
      - token de Claude en /etc/chinesereads-generador.env
      - OAuth del MCP de Canva: necesita tunel SSH, no vale hacerlo
        desde otra maquina (docs/despliegue.md, "El OAuth de Canva")
      - systemctl enable --now chinesereads-generador.timer

 Comprobar cómo va todo:
   sudo -u ${USUARIO} python3 ${DESTINO}/publicador.py estado
   systemctl list-timers 'chinesereads-*'
════════════════════════════════════════════════════════════════════
FIN
