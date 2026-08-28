#!/bin/bash
# Generación autónoma de un post con Claude Code en modo headless.
#
# Pensado para un cron en el VPS ANTES del cron de publicación (p. ej. 7:00
# generar, 8:00 publicar). Solo genera si la cola está vacía: los posts que
# generes tú a mano siempre tienen prioridad y el bot no gasta nada.
#
# Requisitos en el VPS (guía completa en PUBLICACION.md):
#   - Claude Code instalado y autenticado (claude setup-token)
#   - .venv del repo montado y MCP de Canva autorizado (una vez, interactivo)
#   - .pollinations_token y publicacion_config.json presentes
#
# Cron sugerido (crontab -e):
#   CRON_TZ=Europe/Madrid
#   0 7 * * * /ruta/al/repo/generacion_autonoma.sh
#   0 8 * * * cd /ruta/al/repo && /usr/bin/python3 publicador.py publicar >> publicador.log 2>&1

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

# --dangerously-skip-permissions: necesario en headless (no hay nadie que
# apruebe permisos). Ejecutar siempre con un usuario SIN privilegios cuyo
# único cometido sea este repo.
claude -p "$(cat PROMPT_AUTONOMO.md)" \
    --dangerously-skip-permissions \
    >> "$LOG" 2>&1
CODIGO=$?

echo "[$(date '+%F %T')] Generación terminada con código ${CODIGO}. En cola: $(python3 publicador.py pendientes 2>/dev/null || echo '?')" >> "$LOG"
exit "$CODIGO"
