# Documentación

## Un mismo proyecto, dos máquinas

El repositorio es idéntico en tu Mac y en el servidor, y el flujo de
`generar-post` funciona igual en los dos. Lo único que cambia es el campo
`vps.ssh` de `publicacion_config.json`:

- **Relleno (tu Mac)**: al terminar el post, lo sube por `rsync` a la cola
  del servidor.
- **Vacío (el servidor)**: el post se copia a `cola/` sin más, porque ya
  está en la máquina que publica.

Así que puedes pedir posts desde tu ordenador, o dejar que el servidor los
genere solo; el resultado es el mismo y ambos usan las mismas reglas.

## Empezar

| Documento | Para qué |
|---|---|
| [local.md](local.md) | Trabajar en tu Mac: instalar, configurar y pedir posts |
| [despliegue.md](despliegue.md) | Montar el servidor desde cero (un solo comando + qué hace) |
| [configuracion.md](configuracion.md) | **Todos los secretos**: qué necesitas, de dónde sale y dónde va |

## Las redes

| Documento | Para qué |
|---|---|
| [instagram.md](instagram.md) | Cómo se conectó, cómo funciona la autenticación, límites |
| [tiktok.md](tiktok.md) | Lo mismo + el sandbox y **qué queda pendiente** (la auditoría) |
| [publicacion.md](publicacion.md) | Arquitectura de la publicación, formatos, alcance y shadowban |

## Otros

| Documento | Para qué |
|---|---|
| [pollinations.md](pollinations.md) | Generación de imágenes con IA: modelos, precios en pollen |
| [mcp-explicado.html](mcp-explicado.html) | Explicación visual de qué es MCP y cómo encaja aquí |

## Montar todo en un servidor nuevo

1. Descargar `despliegue/deploy.sh` y `sudo bash deploy.sh` → [despliegue.md](despliegue.md)
2. Rellenar credenciales → [configuracion.md](configuracion.md)
3. Comprobar: `sudo bash despliegue/verificar.sh` — compara el servidor
   con el repositorio y revisa permisos y secretos

Para **actualizar** un servidor ya montado, el mismo `deploy.sh`: hace
`git pull`, resincroniza lo que vive fuera del repo y no toca lo que ya
está bien.

## Dónde está lo que no es documentación

- **`SKILL.md`** (en la raíz): el flujo de once pasos que sigue Claude para
  generar un post. Vive en la raíz porque es donde lo busca la skill, no en
  esta carpeta.
- **`PROMPT_AUTONOMO.md`** (en la raíz): el encargo que recibe Claude cuando
  genera un post solo en el servidor. Lo lee `generacion_autonoma.sh` por
  ruta relativa.
- **`despliegue/`**: los ficheros que se copian al servidor (unidades de
  systemd, override de Docker, plantillas) y el script `deploy.sh`.
