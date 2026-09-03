# TikTok: cómo quedó conectado y por qué está en pausa

Estado: **conectado en modo Sandbox desde el 2026-08-29, pausado desde el
2026-09-03.** La integración funciona (publica de verdad en
`@chinesereadsapp`), pero TikTok **rechazó la auditoría** y sin ella la API
solo publica en cuentas privadas. Ver
[Por qué se queda en pausa](#por-qué-se-queda-en-pausa).

TikTok está pausado en `publicacion_config.json` (`"pausada": true`): el
publicador ni lo intenta, así que no falla ni ensucia el log, e Instagram
sigue publicando con normalidad. Los TikToks se suben **a mano desde el
móvil** (ver [Cómo publicar en TikTok mientras tanto](#cómo-publicar-en-tiktok-mientras-tanto)).

---

## Por qué TikTok cuesta más que Instagram

Tres obstáculos que Instagram no tiene:

1. **No hay token en el panel.** Hay que hacer un flujo OAuth completo.
2. **Exige verificar el dominio** desde el que se descargan las imágenes.
3. **La app no se puede ni guardar** sin subir un vídeo de demostración,
   porque el único botón de guardar valida también el formulario de
   revisión. La salida a ese callejón es el **Sandbox**.

## El Sandbox: la pieza clave

TikTok tiene un modo Sandbox pensado exactamente para esto: probar la
integración **sin pasar por revisión**. No es un atajo dudoso — es la vía
que ellos recomiendan, hasta el punto de que el propio formulario de
revisión dice que si la app no ha sido aprobada antes, *debes* usar un
sandbox para grabar la demostración.

Cómo se creó:

1. En la página de la app, el **interruptor junto al nombre** → Sandbox.
2. **Create Sandbox**, con un nombre, clonando la configuración de
   producción (así hereda productos, scopes y redirect URI).
3. **Apply changes**.

Diferencias respecto a producción:

- **Sin sección "App review"**: se guarda sin vídeo ni explicación.
- **Credenciales propias**: su `client_key` empieza por `sb`.
- **Verificación de dominio propia**: emite su propio código TXT.
- **Target Users**: solo puede publicar en cuentas añadidas expresamente
  (Sandbox settings → Target Users → Add account → `@chinesereadsapp`).
- Se pueden crear hasta 5 sandboxes sin afectar a la app de producción.

## Configuración de la app

| Campo | Valor |
|---|---|
| App name | `ChineseReads` |
| Category | Education |
| Description | `Publishing automation for ChineseReads: posts our own Chinese-learning vocabulary carousels to our TikTok account.` |
| Terms of Service | `https://chinesereads.com/terms-of-use` |
| Privacy Policy | `https://chinesereads.com/privacy-policy` |
| Platforms | Web → `https://chinesereads.com` |
| Productos | Login Kit + Content Posting API (con **Direct Post** activado) |
| Scopes | `user.info.basic`, `video.publish` (+ `video.upload`, que viene incluido y no se puede quitar) |
| Redirect URI | `https://chinesereads.com/cola-chinesereads/tiktok-callback.html` |

`video.upload` deja borradores para terminarlos a mano; `video.publish` es
el que publica de verdad y solo aparece al activar **Direct Post**. Nuestro
código nunca llama a `video.upload`.

## Verificación del dominio

Sin esto no funciona `PULL_FROM_URL`, que es como TikTok descarga las
imágenes de la cola. Hay dos métodos; usamos el de **DNS**:

- **Domain** (registro TXT) → verifica el dominio entero y todo lo que
  cuelga de él. **Es el que queremos**, porque cubre a la vez las páginas
  legales, la URL de retorno y las imágenes.
- **URL prefix** (fichero de firma) → solo cubre lo que esté bajo ese
  prefijo exacto. Se descartó: dejaría fuera `/terms-of-use` y
  `/privacy-policy`, y sin ellas el formulario no deja guardar.

En el panel: **Manage URL properties → Domain →** `chinesereads.com` (sin
`https://`, sin `www`, sin ruta). Da un código que se añade como registro
TXT en el DNS del dominio (Hostinger, en nuestro caso: Dominios →
chinesereads.com → Zona DNS → tipo `TXT`, nombre `@`, valor
`tiktok-developers-site-verification=...`).

Comprobar la propagación antes de pulsar "Verify" ahorra intentos fallidos:

```bash
dig @8.8.8.8 +short TXT chinesereads.com
```

**Ojo**: sandbox y producción emiten códigos distintos. Ahora mismo el DNS
tiene el del sandbox; si algún día se pasara a producción habría que
**añadir** (no sustituir) el suyo.

## El flujo de autenticación, paso a paso

Es la parte más artesanal, y solo se hace una vez.

**1. URL de autorización.** Se construye con el `client_key`:

```
https://www.tiktok.com/v2/auth/authorize/
  ?client_key=<CLIENT_KEY>
  &scope=user.info.basic,video.publish     (codificado: %2C en la coma)
  &response_type=code
  &redirect_uri=https://chinesereads.com/cola-chinesereads/tiktok-callback.html
  &state=<cadena aleatoria>
```

**2. El usuario autoriza** en el navegador, con la sesión de la cuenta
iniciada, y TikTok redirige a la `redirect_uri` con un `code` en la URL.
Ese código es de **un solo uso y caduca en minutos**.

Para leerlo cómodamente se publicó una página estática temporal
(`despliegue/tiktok-callback.html`) que muestra el código en pantalla. **Ya
está borrada del servidor**: solo hacía falta para este paso, así que la
superficie expuesta ya no existe.

Es HTML estático sin backend: no guarda nada, no envía nada a ningún sitio
y usa `textContent` (nunca `innerHTML`), de modo que nada de lo que venga
en la URL puede interpretarse como código. Aun así, se borra en cuanto
sobra.

Si hay que repetir el OAuth (cambio a producción, o dentro de un año):

```bash
# 1. Publicar la página otra vez
scp despliegue/tiktok-callback.html root@SERVIDOR:/home/chinesereads/publicador/cola/
ssh root@SERVIDOR 'chown chinesereads: /home/chinesereads/publicador/cola/tiktok-callback.html'

# 2. Autorizar en el navegador con la URL de arriba y canjear el código

# 3. Borrarla en cuanto termines
ssh root@SERVIDOR 'rm /home/chinesereads/publicador/cola/tiktok-callback.html'
```

**3. Canje del código por tokens.** Contra el endpoint de OAuth, con el
`client_secret` (que nunca sale del servidor):

```
POST https://open.tiktokapis.com/v2/oauth/token/
Content-Type: application/x-www-form-urlencoded

client_key=...&client_secret=...&code=...&grant_type=authorization_code
&redirect_uri=https://chinesereads.com/cola-chinesereads/tiktok-callback.html
```

Respuesta: `access_token` (24 h), `refresh_token` (**1 año**), `open_id` y
los scopes concedidos. Todo se guarda en `publicacion_config.json`.

**4. Renovación automática.** `publicacion/publicador.py` renueva el `access_token` en
cada ejecución si está caducado o a punto:

```
POST https://open.tiktokapis.com/v2/oauth/token/
grant_type=refresh_token&refresh_token=...
```

Detalle importante: **el `refresh_token` rota** — cada renovación devuelve
uno nuevo y hay que guardarlo, cosa que el publicador hace. Mientras el
sistema publique con regularidad, la autenticación se mantiene sola.

## Cómo se publica un carrusel de fotos

1. `POST /v2/post/publish/creator_info/query/` — **obligatorio** antes de
   publicar; devuelve la cuenta y qué privacidades admite.
2. `POST /v2/post/publish/content/init/` con `media_type: PHOTO`,
   `post_mode: DIRECT_POST`, `source: PULL_FROM_URL` y la lista de URLs.
3. Sondear `POST /v2/post/publish/status/fetch/` hasta
   `PUBLISH_COMPLETE`.

Límites: hasta 35 fotos, **máximo 1080p y 20 MB por imagen**, formatos
**JPEG o WebP** (nada de PNG), título de 90 caracteres y descripción de
4000. Por eso `preparar_para_cola` convierte a JPEG de 1080 px.

## De dónde salen estos endpoints

Ninguno se adivina: están en la documentación oficial, en
[developers.tiktok.com](https://developers.tiktok.com/doc/overview). Si un
día tienes que buscarlos tú:

- **Menú lateral → Login Kit → Manage User Access Tokens**: la URL de
  autorización, el endpoint de canje y el de refresco.
- **Menú lateral → Content Posting API → Get Started / Photo Post**: los
  tres endpoints de publicación y sus parámetros.
- **Content Posting API → Media Transfer Guide**: los límites de formato,
  tamaño y resolución, y cómo funciona `PULL_FROM_URL`.

Un truco general: casi todas las APIs versionan por ruta
(`/v2/...`), así que si algo deja de funcionar, lo primero es mirar si
cambió la versión. Y desconfía de los tutoriales de blogs: en este proyecto
varios daban por obligatoria una página de Facebook para Instagram que ya
no hace falta desde 2024.

## Por qué se queda en pausa

Sin auditoría (app review), la API **no publica en cuentas públicas**.
Comprobado en el primer intento real (2026-08-29):

```
HTTP 403 ... {"error":{"code":"unaudited_client_can_only_post_to_private_accounts"}}
```

No depende de nuestro `privacy_level`, sino de la **privacidad de la
cuenta**: mientras `@chinesereadsapp` sea pública, la API se niega. Solo
publicaría con la cuenta en privado y el post como `SELF_ONLY`, lo que no
sirve para una cuenta pública que publica a diario.

**La auditoría se envió el 2026-08-29 y fue rechazada el 2026-09-03** con
este motivo:

> App will not be approved for personal or company internal use. TikTok for
> Developers currently does not support personal or internal company use.

No es un problema de redacción ni de vídeo: es política de TikTok. **No
aprueban apps cuyo uso sea publicar en la cuenta del propio desarrollador**,
que es exactamente lo que hace esta. Volver a enviarla con el mismo caso de
uso da el mismo resultado. Solo tendría sentido reintentarlo si algún día la
web ChineseReads ofreciera de verdad a sus usuarios "compartir en TikTok";
inventar ese caso de uso para pasar la revisión no es una opción.

Lo que queda montado (app, sandbox, dominio verificado, OAuth, código del
publicador) no se ha desmontado: sigue en el repo por si TikTok cambia de
política o aparece un caso de uso legítimo. La explicación del formulario
sigue guardada en [configuracion.md](configuracion.md).

Si algún día se aprobara, los pasos serían:

1. Añadir al DNS el código TXT de la app de **producción**.
2. Cambiar `client_key` y `client_secret` en `publicacion_config.json` por
   los de producción (los del sandbox dejan de valer).
3. Repetir el OAuth una vez (volver a subir la página de retorno).
4. Cambiar `"privacy_level"` a `"PUBLIC_TO_EVERYONE"` y quitar `"pausada"`.

## Cómo publicar en TikTok mientras tanto

**A mano, desde el móvil.** El post del día ya está en Canva, en la carpeta
`chinesereads-posts`, con el nombre `tema-fecha` (ejemplo:
`deportes-2026-09-03`). Desde la app de Canva en el móvil: abrir el diseño,
descargarlo como imágenes (JPG o PNG, todas las páginas) y subirlas a TikTok
como carrusel de fotos con el mismo texto que llevó Instagram. Ese texto
está en `meta.json`, dentro de la carpeta del post en `publicados/`
del VPS, y también es el que aparece publicado en Instagram, de donde es
más cómodo copiarlo.

Lo que **no** sale a cuenta:

- **Metricool** (partner auditado de TikTok) publica en público, pero hay
  que arrastrar los JPEG desde un ordenador. Más lío que el móvil.
- **Intermediarios con app auditada** (Upload-Post, Ayrshare y similares)
  permitirían dejarlo automático llamando a su API en vez de a la de
  TikTok, pero ninguno es gratis para TikTok: desde unos 16 $/mes el más
  barato (comprobado el 2026-09-03). Si algún día compensa, el cambio es
  solo en la parte de TikTok de `publicacion/publicador.py`.
- **Postiz, Mixpost y demás autoalojados**: necesitan tu propia app de
  TikTok, así que chocan con el mismo rechazo.
