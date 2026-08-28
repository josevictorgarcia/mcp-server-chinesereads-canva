# Pollinations: pollen, precios y qué pasa sin saldo

Notas operativas del servicio de generación de imágenes que usa
`generar_imagen_ia`. Verificado contra la API real el 2026-08-27; los precios
salen del catálogo vivo (`gen.pollinations.ai/image/models`), no de la
documentación, que va por detrás del producto.

## Qué es el pollen

La moneda **prepago** de Pollinations: 1 pollen ≈ 1 $. Se descuenta de tu
saldo por cada generación en `gen.pollinations.ai` (el endpoint que usa tu
clave `sk_`).

**No existe el saldo negativo.** Al ser prepago, cuando el saldo llega a 0 el
servicio simplemente rechaza la petición con HTTP 402 ("Insufficient
balance") y no genera nada. Comprobado empíricamente con saldo 0.0000: no te
quedas "en rojo" ni te pueden cobrar nada — no hay método de pago asociado
que cargar.

Además, este proyecto no se rompe sin saldo: `generar_imagen_ia` detecta el
402 y cae automáticamente al endpoint clásico anónimo (gratis, modelo
pequeño a 768×768), avisando en `avisos`.

## Cómo se consigue

Lo que muestra el panel real ([enter.pollinations.ai](https://enter.pollinations.ai))
a fecha 2026-08-27:

1. **Reclamo inicial** por registrarse (una vez): ~3.25 pollen.
2. **Quests**: recompensas puntuales de comunidad (p. ej. dar una estrella a
   su repo de GitHub).
3. **Compra** con tarjeta (ese pollen no caduca).

La FAQ oficial de su GitHub menciona además un "grant diario" por tiers
(seed/flower/nectar), pero **el panel actual no lo muestra** — esa FAQ
también afirma que flux es gratis e ilimitado y la API real lo cobra, así
que está desactualizada. No cuentes con pollen diario: lo fiable es el
saldo del panel.

## Precio por imagen (modelos oficiales, catálogo vivo 2026-08-27)

Los modelos de difusión cobran una tarifa plana por imagen (verificado: el
402 de una petición de flux estimaba exactamente 0.002):

| Modelo | Qué es | Pollen/imagen | Imágenes con 3.25 pollen |
|---|---|---|---|
| `dreamshaper` (alias `sana`) | DreamShaper 8 LCM (el del tier anónimo) | 0.0001 | 32 500 |
| `flux` | FLUX.1 Schnell | 0.002 | 1 625 |
| `zimage` | Z-Image Turbo (Alibaba, el default del servicio) | 0.004 | 812 |
| **`klein`** | **FLUX.2 Klein 4B (nuestro preferido)** | **0.005** | **650** |
| `kontext` | FLUX.1 Kontext Pro (edición de imágenes) | 0.03 | 108 |
| `nova-canvas` | Amazon Nova Canvas | 0.04 (más caro si >1024 px) | 81 |

Los modelos `gptimage*` (OpenAI) cobran **por token**, no por imagen
(0.000006–0.0000225 por token de imagen más el prompt): el coste real por
imagen depende del tamaño y no es predecible de antemano. No los usamos.

Nuestro gasto típico por post: 1 portada con 1-3 intentos de `klein` ≈
**0.005–0.015 pollen** (medio céntimo como mucho). El reclamo inicial da
para cientos de posts.

## Por qué a veces sale una imagen "gratis"

Dos casos reales, por si vuelven a aparecer:

- **Caché**: si alguien ya generó exactamente el mismo prompt con los mismos
  parámetros (modelo, tamaño, seed), el servicio sirve el resultado cacheado
  sin cobrar. Así salió una imagen de prueba con saldo 0.
- **Endpoint clásico** (`image.pollinations.ai`): sigue siendo anónimo y
  gratuito, pero solo sirve el modelo pequeño a 768×768. Es nuestro plan B
  automático.

## La clave y sus permisos

La clave `sk_` local (`.pollinations_token`, en `.gitignore`) tiene **solo el
permiso de modelos** — mínimo privilegio. Consecuencia: el endpoint de saldo
(`/account/balance`) responde 403 con ella; el saldo se mira en el panel. Si
algún día quieres consultarlo desde aquí, añade a la clave el permiso
**Usage** (solo lectura de consumo) — nunca "Account Admin".
