# Ficheros que viven en el VPS

Copias de referencia de todo lo que se instaló **fuera** de este repo en el
servidor de chinesereads.com (`root@65.21.59.130`, Ubuntu 24.04) el
2026-08-28. Están aquí para que nada dependa solo del servidor: si hubiera
que rehacerlo, se copian a su sitio y listo. El detalle del porqué de cada
decisión está en [PUBLICACION.md](../PUBLICACION.md).

| Fichero | Dónde va en el servidor | Para qué |
|---|---|---|
| `docker-compose.override.yml` | `/root/2025-ChineseTexts/docker/` | Publica la cola en `https://chinesereads.com/cola-chinesereads/` montándola en el `/srv` de Caddy |
| `chinesereads-publicador.service` | `/etc/systemd/system/` | Ejecuta `publicador.py publicar` |
| `chinesereads-publicador.timer` | `/etc/systemd/system/` | Lo dispara a las 8:00 hora española |

Lo único que NO está aquí (ni puede estarlo) es
`publicacion_config.json`: contiene los tokens de Instagram y TikTok. Vive
solo en el servidor con `chmod 600` y en tu Mac. Su plantilla vacía es
`publicacion_config.ejemplo.json`, en la raíz del repo.

## Sobre el override de Docker

Es la pieza más delicada, así que conviene entenderla:

- Es un fichero **nuevo y sin versionar** dentro del repo de la web
  (`codeurjc-students/2025-ChineseTexts`). No modifica ningún fichero de
  ese repo — en particular **no toca el `Caddyfile`**, que se actualiza con
  cada `git pull` del despliegue.
- Docker Compose lo fusiona automáticamente con `docker-compose.yml`
  (comportamiento estándar: cualquier `docker-compose.override.yml` en el
  mismo directorio se aplica solo), así que los despliegues normales lo
  respetan sin hacer nada especial.
- Está listado en `/root/2025-ChineseTexts/.git/info/exclude` (exclusión
  local de git, no versionada) para que no aparezca en `git status` ni se
  cuele en un `git add -A` de la web.

Aplicar un cambio en él:

```bash
cd /root/2025-ChineseTexts/docker
docker compose --env-file .env up -d --force-recreate --no-deps caddy
```

Deshacerlo todo (volver al estado original de la web): borrar el fichero y
ejecutar ese mismo comando.

## Comprobaciones útiles

```bash
systemctl list-timers chinesereads-publicador.timer   # próximo disparo
journalctl -u chinesereads-publicador.service -n 30   # qué pasó
systemctl start chinesereads-publicador.service       # publicar ahora
cd /root/chinesereads-publicador && python3 publicador.py estado
docker exec docker-caddy-1 ls /srv/cola-chinesereads  # ¿montaje vivo?
```
