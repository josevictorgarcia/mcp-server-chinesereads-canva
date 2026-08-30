# Trabajar en local (tu Mac)

Cómo dejar tu ordenador listo para pedir posts, que es como se ha trabajado
hasta ahora. El servidor publica; el Mac genera.

---

## Instalación (una vez)

```bash
git clone https://github.com/josevictorgarcia/mcp-server-chinesereads-canva.git
cd mcp-server-chinesereads-canva
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

**Conecta el MCP de Canva** (OAuth en el navegador, sin crear ninguna app).
No hay que dar de alta nada: **los dos servidores ya vienen declarados en
`.mcp.json`** —`catalogo-plantillas`, que Claude Code levanta solo, y `canva`—
así que al abrir el proyecto solo hay que aprobarlos y luego autenticar Canva:

```
/mcp        → canva → Authenticate → autorizas en el navegador
```

Comprueba con `/mcp` que los dos aparecen conectados. Si Canva dice *Needs
authentication*, repite ese mismo paso: el token caduca cada cierto tiempo.

## Configuración local

Dos ficheros, ninguno en git:

**`publicacion_config.json`** — en el Mac solo sirve para saber a qué
servidor subir la cola y qué hashtags usar por defecto. Las credenciales van
**vacías**: el Mac no publica nada.

```json
{
  "base_url_publica": "https://chinesereads.com/cola-chinesereads",
  "vps": {
    "ssh": "root@65.21.59.130",
    "ruta_cola": "/home/chinesereads/publicador/cola"
  },
  "instagram": { "user_id": "", "access_token": "", "token_refrescado": "" },
  "tiktok": { "client_key": "", "client_secret": "", "refresh_token": "", "privacy_level": "SELF_ONLY" },
  "hashtags_por_defecto": ["#learnchinese", "..."]
}
```

Necesitas **acceso ssh por llave** al servidor para que el `rsync` funcione
sin contraseña:

```bash
ssh-keygen -t ed25519            # si aún no tienes llave
ssh-copy-id root@65.21.59.130    # pide la contraseña una vez
```

Ojo: ese `ssh-copy-id` **hay que ejecutarlo en la app Terminal**, no desde
el prompt de Claude Code — ahí no hay terminal interactivo y la petición de
contraseña falla sin explicación.

**`.pollinations_token`** — la clave para generar las portadas con IA. Ver
[configuracion.md](configuracion.md).

## Pedir un post

Dentro de la carpeta del proyecto, en Claude Code:

```
> hazme un post de 5 palabras en chino sobre deportes
```

La skill `generar-post` se dispara sola y hace los once pasos: elegir
plantilla, pedir el contrato de huecos, generar el contenido, validarlo,
duplicar y editar en Canva, exportar, portada, slide final, registrar en el
historial, encolar en el servidor y resumir.

Al final te enseña las imágenes y la caption exacta. El post se publicará a
las 20:00 del primer día en que sea el más antiguo de la cola; si quieres
retenerlo, se le pone `no_publicar_antes_de`.

## Después de tocar `servidor_catalogo.py`

El servidor MCP local corre como un subproceso que se levantó al abrir la
sesión: **si se añaden o cambian herramientas, hay que reconectar con
`/mcp`**, o Claude seguirá viendo la versión antigua. Es la causa más común
de "esa herramienta no existe".

`/mcp` se escribe en tu sesión interactiva de Claude Code —la de tu Mac— y
reconecta los dos servidores del proyecto a la vez. **En el servidor no hace
falta**: allí cada generación arranca un proceso nuevo, que siempre lee el
código actual.

## Comprobar que el servidor local funciona

```bash
./.venv/bin/python -c "
import servidor_catalogo as s
print(s.listar_plantillas())
print(s.preparar_encargo('texto-3', 'animales', 4))
print(s.elementos_usados('texto-3'))
print(s.portadas_recientes())
"
```

Debe listar tus plantillas y devolver el contrato de una petición de 4
slides para `texto-3`.

Para comprobar además el cálculo de contraste que decide el color del título,
pásale la ruta de una portada que tengas ya descargada:

```bash
./.venv/bin/python -c "
import servidor_catalogo as s
print(s.elegir_color_titulo('posts/naturaleza-2026-08-30/portada-candidata.png'))
"
```

## Qué se queda en el Mac y qué no

- **Se queda**: los PNG a máxima calidad en `posts/<tema>-<fecha>/`, las
  imágenes de IA descartadas en `posts/descartes/`, y `historial.json`.
- **Viaja al servidor**: solo la carpeta `_cola/` con los JPEG de 1080 px y
  el `meta.json`.
- **No está en el Mac**: ninguna credencial de Instagram ni TikTok.

`historial.json` vive en las dos máquinas y el flujo lo sincroniza con
`rsync -a --update` (baja antes de generar, sube después de registrar), para
que el generador autónomo del servidor y tú no repitáis contenido.

## Copia de seguridad

Lo único irreemplazable de tu Mac es **`historial.json`**: no está en git
(contiene enlaces de edición de Canva) y no se puede regenerar. Cópialo de
vez en cuando a algún sitio privado. Todo lo demás se recupera: el código
con `git clone`, los diseños desde Canva y las credenciales regenerándolas
en los paneles.
