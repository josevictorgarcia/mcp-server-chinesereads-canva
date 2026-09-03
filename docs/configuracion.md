# Configuración manual: todos los secretos, en un solo sitio

Todo lo que hay que rellenar a mano después de ejecutar
[`despliegue/deploy.sh`](../despliegue/deploy.sh). **Nada de esto está en
GitHub ni puede estarlo**: son credenciales. Este documento dice qué
necesitas, de dónde sale y dónde va.

Si mañana cambias de servidor: ejecutas el script, repasas esta lista y
está todo.

---

## Resumen: los cuatro secretos

| Qué | Dónde vive | Permisos | Cómo se consigue |
|---|---|---|---|
| Token de Instagram | `publicacion_config.json` → `instagram` | 600 | [instagram.md](instagram.md) |
| Credenciales de TikTok | `publicacion_config.json` → `tiktok` | 600 | [tiktok.md](tiktok.md) |
| Clave de Pollinations | `.pollinations_token` | 600 | [pollinations.md](pollinations.md) |
| Token de Claude | `/etc/chinesereads-generador.env` | 600, de root | `claude setup-token` |

Los tres primeros viven en la carpeta del proyecto
(`/home/chinesereads/publicador/`), fuera de la carpeta pública. El cuarto
vive en `/etc/` y es de **root** a propósito: systemd lo lee antes de bajar
privilegios, así que ni siquiera el usuario del proyecto puede leerlo.

Ninguno viaja jamás al navegador ni aparece en logs.

---

## 1. `publicacion_config.json`

El fichero central. Se crea solo a partir de
`despliegue/publicacion_config.ejemplo.json` al ejecutar el script; solo hay que
rellenar los huecos.

```jsonc
{
  "base_url_publica": "https://chinesereads.com/cola-chinesereads",
  "dias_retencion": 7,          // días antes de borrar un post ya publicado
  "vps": {
    "ssh": "",                  // VACÍO en el servidor; en el Mac, root@IP
    "ruta_cola": ""             // VACÍO en el servidor; en el Mac, la ruta de cola/
  },
  "instagram": {
    "user_id": "",              // se obtiene con el token, ver instagram.md
    "access_token": "",         // token de larga duración (60 días, se renueva solo)
    "token_refrescado": ""      // lo gestiona el publicador, dejar vacío
  },
  "tiktok": {
    "client_key": "",           // del panel de la app (sandbox: empieza por sb)
    "client_secret": "",        // del panel de la app
    "access_token": "",         // lo rellena el OAuth (dura 24 h)
    "access_token_caduca": "",  // lo gestiona el publicador
    "refresh_token": "",        // lo rellena el OAuth (dura 1 año, rota solo)
    "privacy_level": "SELF_ONLY" // PUBLIC_TO_EVERYONE solo con auditoría aprobada
  },
  "hashtags_por_defecto": ["#learnchinese", "..."]
}
```

**La diferencia Mac / servidor**: en el servidor, `vps.ssh` y
`vps.ruta_cola` van **vacíos** (es el propio servidor, y así el publicador
sabe que puede limpiar `posts/`). En el Mac van rellenos y las secciones de
credenciales quedan **vacías**: el Mac no publica, solo encola.

Tras editarlo:

```bash
chmod 600 publicacion_config.json
python3 publicacion/publicador.py estado     # debe listar las redes configuradas
```

## 2. `.pollinations_token`

La clave de generación de imágenes (`sk_...`), en la raíz del proyecto:

```bash
echo "TU_CLAVE_SK" > .pollinations_token
chmod 600 .pollinations_token
```

Se saca en [enter.pollinations.ai](https://enter.pollinations.ai) con
GitHub, **solo con permiso de modelos** (nunca Account Admin). Sin ella el
sistema sigue funcionando: cae al endpoint anónimo gratuito, con un modelo
más pequeño. Detalles y precios en [pollinations.md](pollinations.md).

## 3. `/etc/chinesereads-generador.env`

Solo si quieres **generación autónoma**. Dos vías, excluyentes:

```bash
# (a) Tu suscripción de Claude — recomendada, sin factura nueva
claude setup-token                 # imprime una URL; la abres en tu ordenador
echo 'CLAUDE_CODE_OAUTH_TOKEN=el-token-que-imprimio' > /etc/chinesereads-generador.env

# (b) Clave de API con facturación propia
echo 'ANTHROPIC_API_KEY=sk-ant-...' > /etc/chinesereads-generador.env

chmod 600 /etc/chinesereads-generador.env
systemctl enable --now chinesereads-generador.timer
```

Opcionalmente, añade `CLAUDE_MODELO=sonnet` (más barato) o `opus` (máxima
calidad) a ese mismo fichero.

**No es lo mismo una cosa que la otra**: el token de suscripción es tu
cuenta funcionando en el servidor (mismos modelos y límites, consumo contra
tu cuota); la clave de API es una cuenta de facturación aparte, con saldo
propio y pago por uso.

## 4. OAuth del MCP de Canva

No es un fichero de texto: es una autorización que se hace **una vez, con
navegador**, y queda guardada en `~/.claude` del usuario del servicio. Solo
hace falta para la generación autónoma.

**Hazla como el usuario del servicio, no copies credenciales de otro
usuario.** Copiar `~/.claude` y `~/.claude.json` de `root` parece funcionar
—el token de acceso vivo sigue valiendo un rato— pero caduca y no se puede
renovar, y la generación autónoma se cae con `canva: Needs authentication`
(comprobado el 2026-08-29). Si ves eso en `claude mcp list`, o
`~/.claude/mcp-needs-auth-cache.json` con una entrada de `canva`, hay que
repetir esta autorización.

Se hace con un túnel SSH al puerto 3118 desde tu Mac; el procedimiento
paso a paso está en [despliegue.md → El OAuth de Canva](despliegue.md#el-oauth-de-canva-una-sola-sesión-y-es-la-del-servidor).
**Y ojo: Canva admite una sola sesión por cliente OAuth.** Autorizar Canva
en el Mac echa al servidor, y al revés: la sesión que manda es la del
servidor.

Si `claude mcp list` dice *"Pending approval"*, los servidores de
`.mcp.json` necesitan aprobación por usuario y ruta. Sin interfaz:

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
```

Los dos servidores del proyecto deben salir `✔ Connected`.

## 5. `historial.json` (no es un secreto, pero es irreemplazable)

La memoria anti-repetición: palabras, temas, portadas y slides finales ya
usadas, más los enlaces de edición de Canva. **No está en git** (contiene
enlaces privados) y **no se puede regenerar**: si se pierde, el sistema
sigue funcionando pero podría repetir contenido.

Al montar un servidor nuevo, tráetelo de la máquina anterior:

```bash
rsync -a historial.json root@NUEVO_SERVIDOR:/home/chinesereads/publicador/
ssh root@NUEVO_SERVIDOR 'chown chinesereads: /home/chinesereads/publicador/historial.json && chmod 600 /home/chinesereads/publicador/historial.json'
```

Haz copia de vez en cuando en algún sitio **privado** (nunca el repo).

---

## Textos guardados para el formulario de TikTok

Es lo que se envió en la auditoría del 2026-08-29, **rechazada** porque
TikTok no aprueba apps de uso propio (ver [tiktok.md](tiktok.md)). Se guarda
por si algún día cambia la política o el caso de uso. La explicación de cómo
se usa cada producto y scope, dentro del límite de 1000 caracteres:

```
ChineseReads (chinesereads.com) is a free web app for learning Chinese through graded reading. We publish daily educational carousels (Chinese character, pinyin and meaning) to our own TikTok account, @chinesereadsapp.

Login Kit / user.info.basic: used once, so the account owner can authorise the app. We read only the open_id to identify the target account, and query creator_info before every post as the documentation requires.

Content Posting API / video.publish: used for Direct Post of photo carousels. The images are designed in Canva, exported as JPEG (1080x1080) and served from our verified domain chinesereads.com, then posted with PULL_FROM_URL.

We only publish our own original educational material to our own account: no third-party, user-generated or promotional content. video.upload is bundled with the product but our integration never calls it.
```

---

## Comprobación final

Con todo puesto:

```bash
sudo -u chinesereads python3 /home/chinesereads/publicador/publicacion/publicador.py estado
```

Debe decir `Redes configuradas: instagram, tiktok` y la URL pública
correcta. Y para ver que la cola se sirve de verdad:

```bash
echo hola > /home/chinesereads/publicador/cola/prueba.txt
curl https://chinesereads.com/cola-chinesereads/prueba.txt   # → hola
rm /home/chinesereads/publicador/cola/prueba.txt
```
