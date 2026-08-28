# Instagram: cómo quedó conectado

Estado: **funcionando en producción desde el 2026-08-28.** La cuenta
publica sola, en público, sin ninguna limitación pendiente.

Primer post publicado por la API:
[instagram.com/p/DcmL99xDB5O](https://www.instagram.com/p/DcmL99xDB5O/)

---

## Qué se usó y por qué

Instagram tiene **dos APIs distintas** para publicar, y elegir la
equivocada cuesta horas:

| API | Requisitos | ¿La usamos? |
|---|---|---|
| Instagram API **with Instagram Login** | Cuenta profesional | **Sí** |
| Instagram API with **Facebook Login** | Cuenta profesional **+ página de Facebook vinculada** | No |

La primera existe desde finales de 2024 y **no necesita página de
Facebook**. Mucha documentación de internet sigue explicando la segunda,
que era la única que había antes; si te topas con guías que exigen crear
una página, están desactualizadas.

Lo que sí hace falta es un **perfil de Facebook** (facebook.com) para
entrar en el portal de desarrolladores. Ojo con la trampa: una "cuenta de
Meta" con email —la de Quest/Horizon— **no vale**; developers.facebook.com
exige un perfil de Facebook. El perfil puede estar vacío: sin
publicaciones, sin amigos y sin página.

## El proceso, tal cual se hizo

1. **Cuenta de Instagram profesional.** `@chinesereadsapp` ya era Business
   (categoría Education). Se cambia gratis en la app: Configuración → Tipo
   de cuenta y herramientas.
2. **Perfil de Facebook** creado para actuar de identidad de desarrollador.
3. **Registro como desarrollador**: developers.facebook.com → "Get
   Started" arriba a la derecha. Sin este paso no aparece el menú "My
   Apps".
4. **Crear la app**: My Apps → Create App → nombre `chinesereads-publisher`
   → caso de uso **Instagram**. Con marcar solo ese caso de uso basta: ya
   trae los permisos necesarios. (Límite: 15 apps por cuenta de
   desarrollador, contando las archivadas.)
5. **Generar el token**: menú lateral → **Instagram → API setup with
   Instagram login** → "Add account" para conectar `@chinesereadsapp` →
   "Generate token". Los permisos concedidos son
   `instagram_business_basic` e `instagram_business_content_publish`.
6. **Guardar el token** en el servidor (nunca en git):
   `publicacion_config.json` → `instagram.access_token`.
7. El **User ID** numérico no hace falta buscarlo por el panel: se obtiene
   con el propio token, y de paso confirma que funciona:

   ```bash
   curl -s "https://graph.instagram.com/v23.0/me?fields=user_id,username,account_type&access_token=TU_TOKEN"
   ```

   Devolvió `user_id: 17841438370317568`, `username: chinesereadsapp`,
   `account_type: BUSINESS`.

**No hizo falta App Review.** La revisión de Meta solo es necesaria para
publicar en cuentas de terceros; para publicar en la tuya propia con la app
en modo desarrollo, no.

## Cómo funciona la autenticación (y por qué no caduca)

El token que da el panel es de **larga duración: 60 días**. Pero
`publicador.py` lo renueva solo: cada vez que publica, si han pasado más de
7 días desde la última renovación, llama a

```
GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=...
```

y guarda el token nuevo con otros 60 días. Mientras el temporizador siga
corriendo, **nunca caduca**. Si el sistema estuviera parado más de 60 días,
habría que generar otro token en el panel (2 minutos).

## Cómo se publica un carrusel

Instagram no recibe ficheros: **descarga las imágenes de una URL pública**.
Por eso la cola se sirve desde `https://chinesereads.com/cola-chinesereads/`
(ver [publicacion.md](publicacion.md)). La secuencia por post es:

1. Un **contenedor hijo** por imagen:
   `POST /{user_id}/media` con `image_url` e `is_carousel_item=true`.
2. Esperar a que cada hijo pase a `status_code: FINISHED`
   (`GET /{id}?fields=status_code`).
3. Un **contenedor padre**: `POST /{user_id}/media` con
   `media_type=CAROUSEL`, `children=<ids>` y el `caption`.
4. **Publicar**: `POST /{user_id}/media_publish` con `creation_id`.

Todo esto lo hace `publicador.py`; aquí está por si algún día hay que
depurarlo a mano.

## Límites que nos afectan

- **Máximo 10 imágenes por carrusel.** Un post de 6 palabras con portada y
  slide final son 8: sobra margen. Si un día se pasara, el publicador
  publica las 10 primeras y lo avisa en el log.
- **Solo JPEG.** La documentación es literal: *"JPEG is the only image
  format supported"*. Nuestros PNG de Canva no valen, por eso el paso 10
  del flujo los convierte con `preparar_para_cola`.
- **100 publicaciones por API al día.** Hacemos una.

## Qué queda pendiente

Nada. Instagram está completo.

La única tarea de mantenimiento imaginable: si algún día el token se
invalida (cambio de contraseña, revocación de permisos), se genera otro en
el panel y se actualiza `publicacion_config.json`. El síntoma sería un
error `Invalid OAuth access token` en `journalctl -u
chinesereads-publicador.service`.
