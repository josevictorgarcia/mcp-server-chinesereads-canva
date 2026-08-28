#!/bin/bash
# Generación autónoma de un post con Claude Code en modo headless.
#
# Se dispara en el VPS una hora ANTES de la publicación (19:00 generar,
# 20:00 publicar). Solo genera si la cola está vacía: los posts que
# generes tú a mano siempre tienen prioridad y el bot no gasta nada.
#
# Requisitos en el VPS (guía completa en docs/despliegue.md):
#   - Claude Code instalado y autenticado (claude setup-token)
#   - .venv del repo montado y MCP de Canva autorizado (una vez, interactivo)
#   - .pollinations_token y publicacion_config.json presentes
#
# Disparo: timer de systemd a las 19:00 Europe/Madrid, una hora antes del de
# publicación (ver docs/publicacion.md). Con cron NO: el de Debian/Ubuntu ignora
# CRON_TZ y el servidor va en UTC, así que el horario de verano desplazaría
# la hora dos veces al año.

set -u
cd "$(dirname "$0")"
LOG=generacion.log

echo "[$(date '+%F %T')] --- generación autónoma ---" >> "$LOG"

PENDIENTES=$(python3 publicador.py pendientes 2>/dev/null || echo 0)
if [ "${PENDIENTES:-0}" -ge 1 ]; then
    echo "[$(date '+%F %T')] Cola con ${PENDIENTES} post(s): no hace falta generar." >> "$LOG"
    exit 0
fi

if ! command -v claude >/dev/null 2>&1; then
    echo "[$(date '+%F %T')] ERROR: claude no está instalado en el PATH." >> "$LOG"
    exit 1
fi

# CLAUDE_MODELO permite fijar el modelo (p. ej. "sonnet" para abaratar la
# generación diaria, u "opus" para la máxima calidad). Si no se define, se
# usa el que Claude Code tenga por defecto.
MODELO_ARG=""
if [ -n "${CLAUDE_MODELO:-}" ]; then
    MODELO_ARG="--model ${CLAUDE_MODELO}"
fi

# --dangerously-skip-permissions: necesario en headless (no hay nadie que
# apruebe permisos). Ejecutar siempre con un usuario SIN privilegios cuyo
# único cometido sea este repo.
# shellcheck disable=SC2086  # MODELO_ARG debe expandirse en dos palabras
claude -p "$(cat PROMPT_AUTONOMO.md)" \
    $MODELO_ARG \
    --dangerously-skip-permissions \
    >> "$LOG" 2>&1
CODIGO=$?

echo "[$(date '+%F %T')] Generación terminada con código ${CODIGO}. En cola: $(python3 publicador.py pendientes 2>/dev/null || echo '?')" >> "$LOG"
exit "$CODIGO"
