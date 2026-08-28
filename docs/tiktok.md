# TikTok: cómo quedó conectado y qué falta

Estado: **conectado y funcionando en modo Sandbox desde el 2026-08-29.**
Publica de verdad en `@chinesereadsapp`, pero los posts salen en **privado**
(`SELF_ONLY`) hasta que TikTok apruebe la auditoría. Ver
[Lo que queda pendiente](#lo-que-queda-pendiente).

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
tiene el del sandbox; cuando se envíe producción a revisión habrá que
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
está borrada del servidor**: solo hacía falta para este paso. Si algún día
hay que repetir el OAuth, se vuelve a subir a `cola/` y se borra después.

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

**4. Renovación automática.** `publicador.py` renueva el `access_token` en
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

## Lo que queda pendiente

**La auditoría (app review).** Es lo único. Sin ella, todo funciona pero
los posts salen en privado; tú los haces públicos desde la app del móvil
con dos toques, o los dejas así.

Para pedirla hacen falta dos cosas que ahora ya se pueden preparar:

1. **La explicación** (máx. 1000 caracteres) — redactada y lista en
   [configuracion.md](configuracion.md).
2. **Un vídeo demostrando el flujo completo**, grabado desde el Sandbox.
   Basta una captura de pantalla enseñando: el post generado, la cola, el
   comando publicando y el resultado apareciendo en TikTok.

Consejos para que no la rechacen: describe un caso de uso concreto (nada
de "gestión de redes sociales" en abstracto), deja claro que publicas
**contenido propio en tu propia cuenta**, y no dejes marcados scopes que no
demuestres en el vídeo.

Plazo típico: **2 a 6 semanas**. Mientras tanto no bloquea nada.

Cuando la aprueben:

1. Añadir al DNS el código TXT de la app de **producción**.
2. Cambiar `client_key` y `client_secret` en `publicacion_config.json` por
   los de producción (los del sandbox dejan de valer).
3. Repetir el OAuth una vez (volver a subir la página de retorno).
4. Cambiar `"privacy_level"` a `"PUBLIC_TO_EVERYONE"`.

Curiosidad útil: `creator_info` ya informa de que la cuenta admite
`PUBLIC_TO_EVERYONE`, pero eso describe la cuenta, no los permisos de la
app. Los clientes sin auditar siguen forzados a privado.

## Alternativa mientras tanto: Metricool

Si quieres TikToks **públicos** desde ya, Metricool (que ya tienes) es
partner auditado de TikTok: arrastras los JPEG de `_cola/` a su calendario
y los programa. No sustituye a nada de lo montado aquí; es solo un puente
manual para los días en que quieras publicación pública inmediata.

Lo que **no** sirve es su API: el plan Advanced la incluye para
analíticas, no para publicar programáticamente.
