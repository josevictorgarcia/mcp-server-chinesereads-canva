"""
Servidor MCP local: catálogo de plantillas de Canva.

Este servidor NO habla con Canva. De eso se encarga el servidor MCP oficial de
Canva (mcp.canva.com/mcp), que se conecta por separado.

Lo que hace este servidor es aportar la lógica que Canva no conoce:

  - qué plantillas tuyas existen y para qué sirve cada una
  - qué huecos de texto tiene cada plantilla y con qué límites
  - qué temas ya has publicado, para no repetirte
  - validación determinista del contenido antes de tocar ningún diseño

La división es deliberada: el modelo genera el contenido, pero las reglas duras
(longitudes, nombres de hueco, duplicados) las comprueba código normal. Un
modelo puede equivocarse contando caracteres; una función no.

Transporte: stdio. El cliente lanza este fichero como subproceso.
Requiere mcp >= 2.0 (en el SDK v2 FastMCP pasó a llamarse MCPServer).
"""

from __future__ import annotations

import json
import os
import random
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

# --------------------------------------------------------------------------
# Rutas de datos
# --------------------------------------------------------------------------

BASE = Path(os.environ.get("CATALOGO_DIR", Path(__file__).parent)).resolve()
PLANTILLAS = BASE / "plantillas.json"
HISTORIAL = BASE / "historial.json"

# Nº de posts recientes por plantilla cuyos identificadores se consideran "en
# cooldown" y no deben repetirse. No es un bloqueo permanente: pasado este número
# de posts, la palabra vuelve a estar disponible.
COOLDOWN_POSTS = 15

# Generación de imágenes con IA (Pollinations.ai). Dos endpoints:
#  - gen.pollinations.ai: la plataforma actual. Requiere la clave sk_ (fichero
#    local en .gitignore) y cobra en "pollen" (flux ~0.002/imagen; el grant
#    diario gratuito de la cuenta da para cientos).
#  - image.pollinations.ai: el endpoint clásico, anónimo y gratis, pero sirve
#    solo el modelo pequeño "sana" a 768x768. Es el plan B automático cuando
#    no hay clave, no hay saldo o el endpoint nuevo falla.
POLLINATIONS_GEN = "https://gen.pollinations.ai"
POLLINATIONS_LEGACY = "https://image.pollinations.ai"
POLLINATIONS_TOKEN_FILE = BASE / ".pollinations_token"
# Orden de preferencia entre los modelos oficiales que anuncie /image/models.
# klein (FLUX.2) primero: en la comparación visual del 2026-08-27 (mismo
# prompt y semilla) dio la imagen más fotográfica; zimage quedó algo plástico
# y flux (FLUX.1 Schnell) más pobre de composición. Los modelos "community"
# (proxies de terceros) se excluyen siempre: ni su calidad ni el destino de
# los prompts están bajo control de Pollinations.
PREFERENCIA_MODELOS_IA = ("klein", "zimage", "flux", "dreamshaper", "sana")
# Pollinations devuelve 403 al User-Agent por defecto de urllib ("Python-urllib");
# uno propio identificable pasa sin problema.
POLLINATIONS_UA = "chinesereads-canva/1.0"

mcp = MCPServer(
    name="catalogo-plantillas",
    instructions=(
        "Catálogo de plantillas propias de Canva. Úsalo para elegir plantilla, "
        "conocer los huecos de texto que admite, validar el contenido generado "
        "y registrar lo ya publicado. Las operaciones sobre los diseños "
        "(duplicar, leer, editar, exportar) se hacen con el servidor MCP de Canva."
    ),
)


# --------------------------------------------------------------------------
# Utilidades internas
# --------------------------------------------------------------------------


def _leer_json(ruta: Path, por_defecto: Any) -> Any:
    if not ruta.exists():
        return por_defecto
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{ruta.name} tiene JSON inválido: {e}") from e


def _escribir_json(ruta: Path, datos: Any) -> None:
    # Escritura atómica: primero a un temporal, luego reemplazo. Evita dejar el
    # fichero a medias si el proceso muere a mitad.
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(ruta)


def _catalogo() -> dict[str, dict]:
    datos = _leer_json(PLANTILLAS, {"plantillas": []})
    return {p["id"]: p for p in datos.get("plantillas", [])}


def _historial() -> list[dict]:
    return _leer_json(HISTORIAL, [])


def _normalizar(texto: str) -> str:
    """Minúsculas sin acentos, para comparar temas de forma tolerante."""
    sin_tildes = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sin_tildes if not unicodedata.combining(c)).strip()


def _buscar(plantilla_id: str) -> dict:
    catalogo = _catalogo()
    if plantilla_id not in catalogo:
        disponibles = ", ".join(catalogo) or "(catálogo vacío)"
        raise ValueError(
            f"No existe la plantilla '{plantilla_id}'. Disponibles: {disponibles}"
        )
    return catalogo[plantilla_id]


# --------------------------------------------------------------------------
# Herramientas
# --------------------------------------------------------------------------


@mcp.tool()
def listar_plantillas() -> list[dict]:
    """Lista las plantillas del catálogo con su tema, formato y número de huecos.

    Punto de partida cuando el usuario pide un post y no dice qué plantilla usar.
    Devuelve una vista resumida; para los detalles llama a obtener_plantilla.
    """
    historial = _historial()
    return [
        {
            "id": p["id"],
            "nombre": p["nombre"],
            "descripcion": p["descripcion"],
            "formato": p.get("formato", "sin especificar"),
            "huecos": len(p.get("huecos", [])),
            "veces_usada": sum(
                1 for h in historial if h.get("plantilla_id") == p["id"]
            ),
        }
        for p in _catalogo().values()
    ]


@mcp.tool()
def obtener_plantilla(plantilla_id: str) -> dict:
    """Devuelve la ficha completa de una plantilla: id del diseño en Canva,
    huecos de texto con sus límites, reglas de estilo e instrucciones de edición.

    Llama a esto ANTES de tocar nada en Canva. El campo canva_design_id es el
    diseño maestro: nunca se edita directamente, siempre se duplica primero.
    """
    p = _buscar(plantilla_id)
    return {
        **p,
        "aviso": (
            "canva_design_id es la plantilla MAESTRA. Duplícala en Canva y edita "
            "la copia. Si el cliente no dispone de una herramienta de duplicado, "
            "pide al usuario que duplique el diseño a mano y te pase el id nuevo."
        ),
    }


@mcp.tool()
def preparar_encargo(plantilla_id: str, tema: str, numero_slides: int) -> dict:
    """Devuelve el contrato que debe cumplir el contenido de un post de N slides:
    huecos a rellenar por slide, reglas de estilo, temas ya usados y palabras en
    cooldown que hay que evitar.

    No genera el contenido. Genéralo tú a partir de este contrato, una vez por
    slide, y valida cada slide de texto con validar_contenido antes de tocar Canva.
    """
    p = _buscar(plantilla_id)

    if numero_slides < 1:
        raise ValueError("numero_slides debe ser al menos 1.")
    max_paginas = p.get("max_paginas")
    if max_paginas and numero_slides > max_paginas:
        raise ValueError(
            f"'{plantilla_id}' admite un máximo de {max_paginas} slides por post "
            f"(has pedido {numero_slides}). Reduce el número o amplía las páginas "
            "de la plantilla maestra en Canva."
        )

    usados = temas_publicados(plantilla_id)
    repetido = _normalizar(tema) in {_normalizar(t) for t in usados}
    recientes = elementos_usados(plantilla_id)

    huecos = p.get("huecos", [])
    huecos_texto = [h for h in huecos if h.get("tipo", "texto") == "texto"]

    return {
        "plantilla_id": plantilla_id,
        "tema": tema,
        "numero_slides": numero_slides,
        "tema_ya_usado": repetido,
        "temas_previos": usados,
        "elementos_recientes": recientes,
        "huecos": huecos,
        "reglas_estilo": p.get("reglas_estilo", []),
        "formato_esperado": {
            "slides": [
                {
                    "identificador": "valor que identifica esta slide, p. ej. la palabra",
                    "contenido": {h["id"]: "texto del hueco" for h in huecos_texto},
                }
                for _ in range(numero_slides)
            ]
        },
        "siguiente_paso": (
            "Genera el contenido de cada slide evitando 'elementos_recientes' y sin "
            "repetir nada entre sí dentro del mismo post. Valida cada slide de texto "
            "con validar_contenido antes de editar nada en Canva."
        ),
    }


@mcp.tool()
def validar_contenido(plantilla_id: str, contenido: dict[str, str]) -> dict:
    """Comprueba que el contenido de UNA slide encaja en la plantilla antes de
    editar en Canva. Solo valida los huecos de texto (los de tipo "imagen" se
    resuelven aparte, buscando/subiendo la imagen directamente en Canva).

    Verifica huecos ausentes, huecos desconocidos, textos vacíos y excesos de
    longitud. Devuelve valido=True o la lista de errores concretos. Si falla,
    corrige y vuelve a validar; no edites el diseño con contenido inválido.
    """
    p = _buscar(plantilla_id)
    huecos = {h["id"]: h for h in p.get("huecos", [])}
    huecos_texto = {
        hid: h for hid, h in huecos.items() if h.get("tipo", "texto") == "texto"
    }

    errores: list[str] = []
    avisos: list[str] = []

    for faltante in huecos_texto.keys() - contenido.keys():
        errores.append(f"Falta el hueco '{faltante}' ({huecos_texto[faltante]['descripcion']}).")

    for sobrante in contenido.keys() - huecos.keys():
        errores.append(
            f"El hueco '{sobrante}' no existe en esta plantilla. "
            f"Válidos: {', '.join(huecos)}."
        )

    for hid, texto in contenido.items():
        if hid not in huecos_texto:
            continue
        if not isinstance(texto, str) or not texto.strip():
            errores.append(f"El hueco '{hid}' está vacío.")
            continue
        limite = huecos_texto[hid].get("max_caracteres")
        if limite and len(texto) > limite:
            errores.append(
                f"'{hid}' tiene {len(texto)} caracteres y el máximo es {limite}. "
                f"Recorta {len(texto) - limite}."
            )
        elif limite and len(texto) > limite * 0.9:
            avisos.append(f"'{hid}' va justo de espacio ({len(texto)}/{limite}).")

    return {
        "valido": not errores,
        "errores": errores,
        "avisos": avisos,
        "longitudes": {k: len(v) for k, v in contenido.items() if isinstance(v, str)},
    }


@mcp.tool()
def temas_publicados(plantilla_id: str | None = None) -> list[str]:
    """Lista los temas de posts ya publicados, opcionalmente filtrados por plantilla.

    Úsalo para no repetir el tema completo de un post (p. ej. "deportes" ya usado
    entero). Para evitar repetir palabras/ítems concretos usa elementos_usados.
    """
    temas = [
        h.get("tema", "")
        for h in _historial()
        if plantilla_id is None or h.get("plantilla_id") == plantilla_id
    ]
    # Sin vacíos ni duplicados, conservando el orden de publicación.
    return list(dict.fromkeys(t for t in temas if t))


@mcp.tool()
def elementos_usados(plantilla_id: str, cooldown: int = COOLDOWN_POSTS) -> list[str]:
    """Identificadores (p. ej. palabras) usados en los últimos `cooldown` posts de
    esta plantilla, más recientes primero. Evítalos al generar contenido nuevo.

    No es una prohibición permanente: fuera de esta ventana de posts, un
    identificador vuelve a estar disponible para no acabar sin vocabulario.
    """
    _buscar(plantilla_id)
    entradas = [h for h in _historial() if h.get("plantilla_id") == plantilla_id]
    recientes = entradas[-cooldown:] if cooldown > 0 else []

    identificadores: list[str] = []
    for entrada in reversed(recientes):
        for slide in entrada.get("slides", []):
            ident = slide.get("identificador")
            if ident:
                identificadores.append(ident)
    return identificadores


@mcp.tool()
def portadas_recientes(cooldown: int = COOLDOWN_POSTS) -> list[dict]:
    """Portadas de los últimos `cooldown` posts (de cualquier plantilla), más
    recientes primero. Cada una trae titulo, imagen y origen.

    Úsalo antes de generar una portada nueva: no reutilices una `imagen` que
    aparezca aquí (misma foto de galería o mismo prompt/semilla de IA) y varía
    la redacción del título respecto a los recientes. Fuera de esta ventana,
    una foto vuelve a estar disponible — igual que el cooldown de palabras.
    """
    entradas = [h for h in _historial() if h.get("portada")]
    recientes = entradas[-cooldown:] if cooldown > 0 else []
    return [
        {
            "titulo": e["portada"].get("titulo", ""),
            "imagen": e["portada"].get("imagen", ""),
            "origen": e["portada"].get("origen", ""),
        }
        for e in reversed(recientes)
    ]


@mcp.tool()
def elegir_final(candidatos: list[str]) -> dict:
    """Elige qué slide final de cierre usar en este post, de entre las
    plantillas disponibles AHORA MISMO en la carpeta de Canva
    chinesereads-plantillas-final (pásale los títulos que devuelva
    list-folder-items sobre esa carpeta; su id está en plantillas.json →
    carpeta_finales_canva_id).

    La rotación es regla de código, no criterio del modelo: gana la candidata
    que lleve más posts sin usarse; si hay varias que no se han usado nunca,
    una de ellas al azar. Así el reparto sigue siendo uniforme aunque el
    usuario añada, borre o renombre plantillas en la carpeta.
    """
    if not candidatos:
        raise ValueError(
            "candidatos está vacío. Si la carpeta de Canva no tiene ninguna "
            "plantilla-final, el post sale sin slide de cierre (no es un "
            "error): sáltate el paso y dilo en el resumen."
        )
    ultimo_uso: dict[str, int] = {}
    for indice, entrada in enumerate(_historial()):
        nombre = (entrada.get("final") or {}).get("nombre")
        if nombre:
            ultimo_uso[nombre] = indice
    nunca_usadas = [c for c in candidatos if c not in ultimo_uso]
    if nunca_usadas:
        elegido = random.choice(nunca_usadas)
        motivo = "no se ha usado nunca"
    else:
        elegido = min(candidatos, key=lambda c: ultimo_uso[c])
        motivo = "es la que lleva más posts sin usarse"
    return {
        "elegido": elegido,
        "motivo": motivo,
        "uso_previo": {
            c: ("nunca" if c not in ultimo_uso else f"post nº {ultimo_uso[c] + 1}")
            for c in candidatos
        },
        "siguiente_paso": ("export-design del diseño elegido (1 página, sin "
                           "editarlo ni copiarlo) → 99-final.png en la carpeta "
                           "del post; regístralo con final={'nombre', "
                           "'design_id'} en registrar_publicacion."),
    }


@mcp.tool()
def analizar_brillo(ruta_imagen: str) -> dict:
    """Mide la luminosidad de una imagen local (0 = negro, 255 = blanco) y
    recomienda el color del título de portada para que se lea bien.

    Devuelve la luminancia global y por tercios horizontales (usa el tercio
    donde va el título en tu plantilla). Regla dura en código, no a ojo del
    modelo: luminancia < 128 → título claro (blanco); >= 128 → título oscuro.
    En la franja intermedia (100-155) el contraste va justo: mantén el degradado
    oscuro de la plantilla o añade sombra al texto.
    """
    from PIL import Image, ImageStat

    ruta = Path(ruta_imagen).expanduser()
    if not ruta.exists():
        raise ValueError(f"No existe el fichero de imagen: {ruta}")

    with Image.open(ruta) as img:
        gris = img.convert("L")
        ancho, alto = gris.size
        tercio = alto // 3

        def _media(caja: tuple[int, int, int, int]) -> float:
            return round(ImageStat.Stat(gris.crop(caja)).mean[0], 1)

        luminancia = {
            "global": round(ImageStat.Stat(gris).mean[0], 1),
            "tercio_superior": _media((0, 0, ancho, tercio)),
            "tercio_central": _media((0, tercio, ancho, 2 * tercio)),
            "tercio_inferior": _media((0, 2 * tercio, ancho, alto)),
        }

    media_global = luminancia["global"]
    return {
        "luminancia": luminancia,
        "titulo_recomendado": "claro" if media_global < 128 else "oscuro",
        "contraste_justo": 100 <= media_global <= 155,
        "nota": (
            "Aplica la recomendación sobre el tercio donde va el título en tu "
            "plantilla, no solo sobre la media global. Si contraste_justo es "
            "true, asegúrate de que el degradado/sombra de la plantilla está ahí."
        ),
    }


def _token_pollinations() -> str:
    try:
        return POLLINATIONS_TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _modelos_pollinations(token: str) -> list[str] | None:
    """Modelos de imagen que Pollinations anuncia ahora mismo, o None si no responde.

    Con clave sk_ pregunta al endpoint nuevo (catálogo completo, filtrando los
    modelos "community" de terceros); sin clave, al clásico (solo el pequeño).
    """
    import urllib.request

    url = (
        f"{POLLINATIONS_GEN}/image/models" if token else f"{POLLINATIONS_LEGACY}/models"
    )
    peticion = urllib.request.Request(url, headers={"User-Agent": POLLINATIONS_UA})
    if token:
        peticion.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(peticion, timeout=15) as resp:
            datos = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if isinstance(datos, dict):
        datos = datos.get("models") or datos.get("data") or []
    if not isinstance(datos, list):
        return None

    nombres: list[str] = []
    for m in datos:
        if isinstance(m, str):
            nombres.append(m)
            continue
        if not isinstance(m, dict) or m.get("community"):
            continue
        if m.get("category", "image") != "image":
            continue
        nombre = m.get("id") or m.get("name") or ""
        if nombre:
            nombres.append(nombre)
    return nombres


@mcp.tool()
def generar_imagen_ia(
    prompt: str,
    ruta_destino: str,
    seed: int | None = None,
    width: int = 1080,
    height: int = 1080,
    modelo: str | None = None,
) -> dict:
    """Genera una imagen con IA (Pollinations.ai) y la descarga a un fichero local.

    Elige solo el mejor modelo oficial disponible en ese momento (el servicio
    anuncia el catálogo en vivo; los "community" de terceros se excluyen), se
    autentica con la clave local si existe y, si no hay clave o no hay saldo de
    pollen, cae solo al endpoint clásico anónimo (modelo pequeño) en vez de
    fallar. Verifica que lo descargado es una imagen real. Devuelve también
    `url_para_canva`: la URL exacta para upload-asset-from-url — SIN la clave,
    porque esta descarga deja la imagen en la caché pública del servicio y de
    ahí la puede leer cualquiera (verificado 2026-08-27).

    Escribe el prompt CON GUIONES en vez de espacios o comas: una URL sin
    caracteres percent-encoded sobrevive intacta a los normalizadores de URLs
    (el fetcher de Canva reescribe las URLs codificadas, falla la caché y
    recibe un 401).

    Después de llamar: MIRA la imagen descargada (léela) antes de usarla. Si sale
    borrosa o deforme, repite con otra `seed`. En el historial registra solo
    prompt+seed, nunca `url_para_canva` (lleva el token).
    """
    import random
    import urllib.error
    import urllib.parse
    import urllib.request

    if not prompt.strip():
        raise ValueError("El prompt no puede estar vacío.")

    token = _token_pollinations()
    disponibles = _modelos_pollinations(token)
    avisos: list[str] = []

    if modelo:
        elegido = modelo
        if disponibles is not None and modelo not in disponibles:
            avisos.append(
                f"'{modelo}' no está entre los modelos anunciados ahora mismo "
                f"({', '.join(disponibles)}); el servicio puede servir otro en su lugar."
            )
    elif disponibles:
        elegido = next(
            (m for m in PREFERENCIA_MODELOS_IA if m in disponibles), disponibles[0]
        )
    else:
        elegido = PREFERENCIA_MODELOS_IA[0]
        avisos.append(
            "El servicio no ha devuelto la lista de modelos (¿caído o saturado?); "
            f"se pide '{elegido}' a ciegas."
        )

    if not token:
        avisos.append(
            "Sin clave sk_: se usa el endpoint clásico anónimo (modelo pequeño, "
            "768x768). Crea una clave en enter.pollinations.ai y guárdala en "
            f"{POLLINATIONS_TOKEN_FILE.name} para acceder a los modelos buenos."
        )

    if seed is None:
        seed = random.randint(1, 999_999_999)

    def _url(endpoint_nuevo: bool, modelo_url: str) -> str:
        comunes = {"model": modelo_url, "width": width, "height": height, "seed": seed}
        if endpoint_nuevo:
            return (
                f"{POLLINATIONS_GEN}/image/{urllib.parse.quote(prompt)}"
                f"?{urllib.parse.urlencode(comunes)}"
            )
        return (
            f"{POLLINATIONS_LEGACY}/prompt/{urllib.parse.quote(prompt)}"
            f"?{urllib.parse.urlencode({**comunes, 'nologo': 'true', 'private': 'true'})}"
        )

    def _descargar(url: str, con_clave: bool) -> bytes:
        peticion = urllib.request.Request(url, headers={"User-Agent": POLLINATIONS_UA})
        if con_clave:
            peticion.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(peticion, timeout=120) as resp:
            return resp.read()

    def _error_servicio(e: Exception) -> ValueError:
        return ValueError(
            f"Pollinations no ha respondido ({e}). El servicio gratuito se satura "
            "a ratos: reintenta una vez y, si sigue caído, pasa a la galería del "
            "usuario o a una foto CC0 de Openverse."
        )

    usa_gen = bool(token)
    url_base = _url(usa_gen, elegido)
    try:
        datos = _descargar(url_base, usa_gen)
    except urllib.error.HTTPError as e:
        if usa_gen and e.code in (401, 402):
            # Sin saldo de pollen (402) o clave rechazada (401): plan B con el
            # endpoint clásico anónimo antes que dejar el post sin imagen.
            motivo = "sin saldo de pollen" if e.code == 402 else "clave rechazada"
            avisos.append(
                f"Endpoint nuevo: {motivo} (HTTP {e.code}). Se usa el endpoint "
                "clásico anónimo (modelo pequeño, 768x768). Revisa el saldo y el "
                "grant diario en enter.pollinations.ai."
            )
            usa_gen = False
            elegido = "sana"
            url_base = _url(False, elegido)
            try:
                datos = _descargar(url_base, False)
            except Exception as e2:
                raise _error_servicio(e2) from e2
        else:
            raise _error_servicio(e) from e
    except Exception as e:
        raise _error_servicio(e) from e

    ruta = Path(ruta_destino).expanduser()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos)

    from PIL import Image

    try:
        with Image.open(ruta) as img:
            resolucion = f"{img.width}x{img.height}"
            exif = img.getexif()
            # Pollinations firma en EXIF qué modelo generó la imagen de verdad
            # (Make/Model); el tier anónimo degrada en silencio, esto lo delata.
            modelo_servido = str(exif.get(271) or exif.get(272) or "").strip()
    except Exception as e:
        ruta.unlink(missing_ok=True)
        raise ValueError(
            f"Lo descargado no es una imagen válida ({e}); probablemente el "
            "servicio devolvió un error. Reintenta o cambia de origen."
        ) from e

    if usa_gen and (" " in prompt or "," in prompt):
        avisos.append(
            "El prompt lleva espacios/comas: la URL queda percent-encoded y el "
            "fetcher de Canva suele romperla (falla la caché → 401). Para subir "
            "a Canva, regenera con el prompt en guiones."
        )

    return {
        "ruta": str(ruta),
        "resolucion": resolucion,
        "endpoint": "gen.pollinations.ai" if usa_gen else "image.pollinations.ai (clásico)",
        "modelo_pedido": elegido,
        "modelo_servido": modelo_servido or "desconocido (sin metadatos EXIF)",
        "seed": seed,
        "prompt": prompt,
        "token_activo": bool(token),
        "modelos_disponibles": disponibles,
        "url_para_canva": url_base,
        "avisos": avisos,
        "siguiente_paso": (
            "Lee (mira) la imagen en 'ruta' antes de usarla; si no convence, "
            "repite con otra seed (2-3 intentos máximo). url_para_canva no "
            "lleva la clave: la imagen ya está en la caché pública del "
            "servicio. Para registrar la portada usa prompt+seed como 'imagen'."
        ),
    }


@mcp.tool()
def registrar_publicacion(
    plantilla_id: str,
    tema: str,
    slides: list[dict],
    url_diseno: str = "",
    notas: str = "",
    portada: dict | None = None,
    final: dict | None = None,
) -> dict:
    """Guarda en el historial un post completo ya creado en Canva (todas sus
    slides de una vez, en una sola llamada por post).

    Llama a esto solo DESPUÉS de que el diseño exista de verdad, con la URL que
    devuelva Canva. Cada elemento de `slides` es un dict con "identificador"
    (lo que identifica esa slide, p. ej. la palabra) y "contenido" (el dict de
    huecos de texto usado). Si el post lleva portada, pásala también:
    {"titulo": "...", "imagen": "<nombre del asset o prompt+seed de IA>",
    "origen": "ia" | "galeria" | "manual"} — es lo que alimenta el cooldown de
    portadas_recientes. Si lleva slide final de cierre, pasa también
    final={"nombre": "<título de la plantilla-final>", "design_id": "..."} —
    es lo que alimenta la rotación de elegir_final. El historial es lo que
    evita que repitas temas, palabras, fotos de portada y slide final.
    """
    _buscar(plantilla_id)  # valida que la plantilla existe

    if not slides:
        raise ValueError("slides no puede estar vacío.")
    for i, slide in enumerate(slides):
        if "identificador" not in slide or "contenido" not in slide:
            raise ValueError(f"slides[{i}] necesita 'identificador' y 'contenido'.")

    if portada is not None:
        for clave in ("titulo", "imagen", "origen"):
            if not portada.get(clave):
                raise ValueError(f"portada necesita '{clave}' (no vacío).")
        if portada["origen"] not in ("ia", "galeria", "manual"):
            raise ValueError("portada['origen'] debe ser 'ia', 'galeria' o 'manual'.")

    if final is not None:
        if not final.get("nombre"):
            raise ValueError("final necesita 'nombre' (el título de la "
                             "plantilla-final usada).")

    entrada = {
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plantilla_id": plantilla_id,
        "tema": tema,
        "slides": slides,
        "url_diseno": url_diseno,
        "notas": notas,
    }
    if portada is not None:
        entrada["portada"] = portada
    if final is not None:
        entrada["final"] = final

    historial = _historial()
    historial.append(entrada)
    _escribir_json(HISTORIAL, historial)

    return {"guardado": True, "total_posts": len(historial), "entrada": entrada}


@mcp.tool()
def anadir_plantilla(
    plantilla_id: str,
    nombre: str,
    descripcion: str,
    canva_design_id: str,
    huecos: list[dict],
    formato: str = "1080x1080",
    reglas_estilo: list[str] | None = None,
    max_paginas: int = 12,
) -> dict:
    """Registra una plantilla nueva en el catálogo sin editar el JSON a mano.

    canva_design_id debe apuntar a un diseño MULTI-PÁGINA (varias páginas con el
    mismo layout duplicadas en Canva): max_paginas es cuántas páginas tiene, y
    limita cuántas slides puede tener un post con esta plantilla.

    Cada hueco es un objeto: {"id": "titulo", "descripcion": "...",
    "max_caracteres": 40, "tipo": "texto"}. El id debe coincidir con el texto que
    ese hueco tiene ahora mismo en cada página del diseño de Canva, para poder
    localizarlo al editar. Usa "tipo": "imagen" (sin max_caracteres) para un hueco
    que se rellena con una imagen en vez de texto.
    """
    datos = _leer_json(PLANTILLAS, {"plantillas": []})

    if any(p["id"] == plantilla_id for p in datos["plantillas"]):
        raise ValueError(f"Ya existe una plantilla con id '{plantilla_id}'.")

    if max_paginas < 1:
        raise ValueError("max_paginas debe ser al menos 1.")

    for h in huecos:
        if "id" not in h or "descripcion" not in h:
            raise ValueError("Cada hueco necesita al menos 'id' y 'descripcion'.")
        tipo = h.get("tipo", "texto")
        if tipo not in ("texto", "imagen"):
            raise ValueError(f"El hueco '{h['id']}' tiene tipo '{tipo}'; debe ser 'texto' o 'imagen'.")
        if tipo == "texto" and not h.get("max_caracteres"):
            raise ValueError(f"El hueco de texto '{h['id']}' necesita max_caracteres.")

    nueva = {
        "id": plantilla_id,
        "nombre": nombre,
        "descripcion": descripcion,
        "canva_design_id": canva_design_id,
        "formato": formato,
        "max_paginas": max_paginas,
        "huecos": huecos,
        "reglas_estilo": reglas_estilo or [],
    }
    datos["plantillas"].append(nueva)
    _escribir_json(PLANTILLAS, datos)

    return {"creada": True, "plantilla": nueva}


if __name__ == "__main__":
    mcp.run(transport="stdio")
