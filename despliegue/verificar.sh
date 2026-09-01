#!/bin/bash
# Comprueba que el servidor es EXACTAMENTE lo que dice el repositorio, y que
# los secretos siguen donde deben. No modifica nada: solo mira e informa.
#
#   sudo bash despliegue/verificar.sh
#
# Devuelve 0 si todo está en orden, 1 si algo no cuadra.

set -u
cd "$(dirname "$0")/.."
PROYECTO="$(pwd)"
USUARIO="$(stat -c %U "$PROYECTO")"
WEB_DOCKER="${CHINESEREADS_WEB_DOCKER:-/root/2025-ChineseTexts/docker}"
FALLOS=0

ok()   { echo "  [ok]    $*"; }
mal()  { echo "  [MAL]   $*"; FALLOS=$((FALLOS+1)); }
nota() { echo "  [nota]  $*"; }

echo "=== 1. Código: repositorio al día y sin cambios locales ==="
sudo -u "$USUARIO" git fetch --quiet origin 2>/dev/null
LOCAL="$(sudo -u "$USUARIO" git rev-parse HEAD)"
REMOTO="$(sudo -u "$USUARIO" git rev-parse origin/main 2>/dev/null || echo "?")"
SUCIO="$(sudo -u "$USUARIO" git status --porcelain)"
[ "$LOCAL" = "$REMOTO" ] && ok "al día con origin/main (${LOCAL:0:7})" \
                         || mal "desincronizado: local ${LOCAL:0:7}, remoto ${REMOTO:0:7} → git pull"
[ -z "$SUCIO" ] && ok "sin cambios locales" \
                || mal "hay cambios locales sin commitear:
$SUCIO"

echo
echo "=== 2. Ficheros fuera del repo: ¿coinciden con despliegue/? ==="
for u in chinesereads-publicador chinesereads-generador; do
    for e in service timer; do
        ESPERADO="$(sed -e "s#/home/chinesereads/publicador#${PROYECTO}#g" \
                        -e "s#^User=chinesereads#User=${USUARIO}#" \
                        -e "s#^Group=chinesereads#Group=${USUARIO}#" \
                        "despliegue/${u}.${e}")"
        if [ ! -f "/etc/systemd/system/${u}.${e}" ]; then
            mal "${u}.${e}: no está instalado"
        elif [ "$ESPERADO" = "$(cat "/etc/systemd/system/${u}.${e}")" ]; then
            ok "${u}.${e}"
        else
            mal "${u}.${e}: difiere del repo → vuelve a ejecutar deploy.sh"
        fi
    done
done

if [ -f "${WEB_DOCKER}/docker-compose.override.yml" ]; then
    ESPERADO="$(sed "s#/home/chinesereads/publicador/cola#${PROYECTO}/cola#" \
                    despliegue/docker-compose.override.yml)"
    [ "$ESPERADO" = "$(cat "${WEB_DOCKER}/docker-compose.override.yml")" ] \
        && ok "docker-compose.override.yml" \
        || mal "docker-compose.override.yml: difiere del repo → deploy.sh"
else
    nota "no hay override de Docker (¿la cola se publica de otro modo?)"
fi

echo
echo "=== 3. Secretos: presentes, con permisos y FUERA de git ==="
comprobar_secreto() {   # $1 ruta  $2 dueño esperado
    if [ ! -s "$1" ]; then
        nota "$1: no existe o está vacío (ver docs/configuracion.md)"
        return
    fi
    PERM="$(stat -c %a "$1")"
    DUENO="$(stat -c %U "$1")"
    if [ "$PERM" = "600" ] && [ "$DUENO" = "$2" ]; then
        ok "$(basename "$1") (600, $DUENO)"
    else
        mal "$(basename "$1"): permisos $PERM y dueño $DUENO (se esperaba 600 y $2)"
    fi
}
comprobar_secreto "${PROYECTO}/publicacion_config.json" "$USUARIO"
comprobar_secreto "${PROYECTO}/.pollinations_token"     "$USUARIO"
comprobar_secreto "${PROYECTO}/historial.json"          "$USUARIO"
comprobar_secreto "/etc/chinesereads-generador.env"     "root"

for f in publicacion_config.json .pollinations_token historial.json; do
    sudo -u "$USUARIO" git check-ignore -q "$f" 2>/dev/null \
        && ok "$f está ignorado por git" \
        || mal "$f NO está en .gitignore: RIESGO de subirlo"
done

echo
echo "=== 4. Nada sensible dentro de la carpeta pública ==="
# cola/ se sirve en internet y solo debe contener CARPETAS de post. Cualquier
# fichero suelto ahí es un resto de algo (la página de callback de TikTok, un
# volcado, un config) y sobra: se comprueba el tipo, no una lista de nombres,
# porque la lista siempre se queda corta.
SOSPECHOSOS="$(find "${PROYECTO}/cola" -maxdepth 1 -type f 2>/dev/null)"
[ -z "$SOSPECHOSOS" ] && ok "cola/ solo contiene carpetas de post" \
                      || mal "hay ficheros sueltos en cola/ (solo debe haber carpetas de post):
$SOSPECHOSOS"

echo
echo "=== 5. Servicio en marcha ==="
if command -v systemctl >/dev/null 2>&1; then
    for t in chinesereads-publicador chinesereads-generador; do
        EST="$(systemctl is-enabled "${t}.timer" 2>/dev/null || echo desconocido)"
        PROX="$(systemctl list-timers "${t}.timer" --no-pager 2>/dev/null | awk 'NR==2{print $1, $2, $3}')"
        [ "$EST" = "enabled" ] && ok "${t}.timer activo → próximo: ${PROX:-?}" \
                              || nota "${t}.timer: $EST"
    done
    # Timers fantasma: los transitorios (systemd-run) viven en /run, no en
    # /etc, así que la comprobación 2 no los ve. Un --on-calendar con comodines
    # ('*-*-* 13:00:00') NO es de un solo uso: se repite todos los días y se
    # queda ahí para siempre. Para publicar una vez, la fecha va completa
    # ('2026-09-01 13:00:00'), que sí se autodestruye.
    EXTRA="$(systemctl list-timers --all --no-pager 2>/dev/null \
             | grep -o 'chinesereads-[a-z-]*\.timer' \
             | grep -v -e 'chinesereads-publicador.timer' \
                       -e 'chinesereads-generador.timer' | sort -u)"
    # Un timer suelto con FECHA COMPLETA (2026-09-01 13:00:00) es legítimo:
    # dispara una vez y se autodestruye. El que hay que cazar es el que lleva
    # comodines, porque ese se repite a diario y no se va nunca.
    if [ -z "$EXTRA" ]; then
        ok "no hay timers de chinesereads fuera de los dos del repo"
    else
        for t in $EXTRA; do
            CAL="$(systemctl cat "$t" 2>/dev/null | grep -m1 '^OnCalendar=' | cut -d= -f2-)"
            case "$CAL" in
                *'*'*) mal "timer recurrente inesperado: $t ($CAL)
  Se repetirá TODOS los días. Quitar con:
    systemctl stop $t && systemctl reset-failed ${t%.timer}" ;;
                *)     nota "$t: disparo único el $CAL, se borra solo al dispararse" ;;
            esac
        done
    fi
fi
# El MCP de Canva es el punto ciego historico: se cae solo (Canva admite una
# sola sesion por cliente OAuth, asi que autorizarlo en el Mac echa al
# servidor) y no se nota hasta que la generacion autonoma aborta de
# madrugada sin encolar nada. Ver docs/despliegue.md.
if command -v claude >/dev/null 2>&1; then
    ESTADO_MCP="$(sudo -H -u "$USUARIO" claude mcp list 2>&1 || true)"
    if echo "$ESTADO_MCP" | grep -q "^canva:.*Connected"; then
        ok "MCP de Canva autorizado"
    else
        mal "MCP de Canva SIN autorizar: la generacion autonoma abortara.
  Reautorizar con tunel SSH (docs/despliegue.md → 'El OAuth de Canva')."
    fi
fi

sudo -u "$USUARIO" python3 publicacion/publicador.py estado 2>&1 | sed 's/^/  /'

echo
if [ "$FALLOS" -eq 0 ]; then
    echo "TODO EN ORDEN: el servidor coincide con el repositorio."
else
    echo "${FALLOS} comprobación(es) fallidas. Revisa arriba."
fi
exit $([ "$FALLOS" -eq 0 ] && echo 0 || echo 1)
