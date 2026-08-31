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

# Color del título de portada. La franja que se mide es la vertical donde cae
# el título en la plantilla (fracciones de la altura): medir la foto entera
# engaña — una foto oscura puede tener nubes claras justo detrás del texto.
BANDA_TITULO = (0.27, 0.60)
# Contraste WCAG mínimo para texto grande (3:1) y mínimo tolerable contra las
# zonas extremas de la franja, que es donde un color plano se rompe.
CONTRASTE_MINIMO = 3.0
CONTRASTE_EXTREMO_MINIMO = 2.0
# La marca de agua de chinesereads no se puede recolorear (va fija en la
# plantilla), así que lo único que se puede hacer para que se lea es elegir la
# variante de portada que la pone sobre una zona donde contraste. Es texto
# pequeño y secundario: le basta con un mínimo más flojo que el del título.
CONTRASTE_MARCA_MINIMO = 2.0
# Rojo real de la marca de agua, medido sobre la plantilla maestra.
MARCA_AGUA_HEX = "#D52E27"
# Por debajo de esta saturación media (0-1) la foto se ve en blanco y negro en
# el feed, aunque el título contraste de sobra.
SATURACION_MINIMA = 0.15
# Una escena de portada (museo, callejón, skyline...) no debe repetirse hasta
# que hayan pasado estos posts. Ventana más larga que la de las palabras: la
# foto es lo primero que se ve en el perfil y es lo que más canta si se repite.
COOLDOWN_ESCENAS = 30

# Número de slides de vocabulario por post. El mínimo evita posts tan cortos
# que no den nada que aprender; el máximo real lo pone `max_paginas` de cada
# plantilla (las páginas que de verdad existen en el diseño maestro de Canva).
MIN_SLIDES = 4
# Un post no puede llevar el mismo número de slides que los últimos posts
# seguidos. Sin esto todos salían de 6 palabras: el modelo, sin dato en
# contra, copia lo último que ve.
COOLDOWN_NUMEROS = 3
# Un ángulo de post (campo semántico, categoría gramatical, situación...) no
# se repite hasta pasados estos posts. Es lo que obliga a alternar entre
# "6 palabras de comida" y "6 preposiciones" o "palabras de los dramas".
COOLDOWN_ANGULOS = 3
# Familias de reserva por si plantillas.json aún no declara `angulos_de_post`.
ANGULOS_POR_DEFECTO = [
    {"id": "campo-semantico", "descripcion": "Vocabulario de un tema concreto."},
]

# Paleta de reserva por si plantillas.json aún no declara `colores_titulo`.
PALETA_TITULO_POR_DEFECTO = [
    {"id": "blanco", "hex": "#FFFFFF", "familia": "claro"},
]

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
    if ruta == HISTORIAL:
        # El historial guarda enlaces de edición de Canva: solo su dueño debe
        # poder leerlo. El reemplazo atómico se lleva los permisos del
        # temporal, así que hay que fijarlos aquí o vuelven a quedar en 644.
        tmp.chmod(0o600)
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


def _plantilla_por_defecto() -> str:
    """La plantilla que se usa salvo que el usuario pida otra explícitamente."""
    return _leer_json(PLANTILLAS, {}).get("plantilla_por_defecto", "")


def _buscar(plantilla_id: str) -> dict:
    catalogo = _catalogo()
    if plantilla_id not in catalogo:
        disponibles = ", ".join(catalogo) or "(catálogo vacío)"
        raise ValueError(
            f"No existe la plantilla '{plantilla_id}'. Disponibles: {disponibles}"
        )
    return catalogo[plantilla_id]


def _paleta_titulo() -> list[dict]:
    """Colores admitidos para el título de portada, desde plantillas.json."""
    portada = _catalogo().get("portada", {})
    paleta = portada.get("colores_titulo") or PALETA_TITULO_POR_DEFECTO
    return [c for c in paleta if c.get("hex")]


def _angulos() -> list[dict]:
    """Familias de ángulo de post declaradas en plantillas.json.

    Es una lista de datos, no de código: el usuario puede añadir o quitar
    familias sin tocar el servidor. La rotación funciona igual.
    """
    crudo = _leer_json(PLANTILLAS, {})
    angulos = crudo.get("angulos_de_post") or ANGULOS_POR_DEFECTO
    return [a for a in angulos if a.get("id")]


def _numeros_recientes(plantilla_id: str, cuantos: int) -> list[int]:
    """Número de slides de los últimos posts de esa plantilla, el más nuevo primero."""
    propias = [e for e in _historial() if e.get("plantilla_id") == plantilla_id]
    return [len(e.get("slides", [])) for e in reversed(propias[-cuantos:])]


def _hex_a_rgb(valor: str) -> tuple[int, int, int]:
    v = valor.strip().lstrip("#")
    if len(v) != 6:
        raise ValueError(f"Color no válido: {valor!r} (formato esperado #RRGGBB).")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_a_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _luminancia_relativa(rgb: tuple[int, int, int]) -> float:
    """Luminancia relativa de la WCAG 2.1 (0 = negro, 1 = blanco)."""
    canales = []
    for valor in rgb[:3]:
        c = valor / 255
        canales.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = canales
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    """Ratio de contraste WCAG entre dos colores (1 = idénticos, 21 = máximo)."""
    l1, l2 = _luminancia_relativa(rgb1), _luminancia_relativa(rgb2)
    claro, oscuro = max(l1, l2), min(l1, l2)
    return (claro + 0.05) / (oscuro + 0.05)


def _extremos(franja_color, columnas: int = 12, filas: int = 4):
    """Color medio del bloque más claro y del más oscuro de la franja.

    La franja se reduce a una rejilla gruesa (12x4) y se comparan bloques, no
    píxeles sueltos: es lo que ve el ojo detrás de un texto grande, y detecta
    los fondos partidos —cielo claro a un lado, montaña oscura al otro— donde
    un color plano contrasta con la media y se pierde igual en media frase.
    """
    from PIL import Image

    rejilla = franja_color.resize((columnas, filas), Image.Resampling.BOX)
    bloques = list(rejilla.getdata())
    claro = max(bloques, key=_luminancia_relativa)
    oscuro = min(bloques, key=_luminancia_relativa)
    return tuple(claro[:3]), tuple(oscuro[:3])


# --------------------------------------------------------------------------
# Herramientas
# --------------------------------------------------------------------------


def _variantes_portada() -> list[dict]:
    """Variantes de la plantilla de portada declaradas en plantillas.json.

    Cada una es el mismo diseño con el título y la marca de agua en sitios
    distintos, así que cada una tiene su propia `banda_titulo` y su
    `banda_marca`. Si no hay lista, se usa la plantilla única de siempre.
    """
    portada = _catalogo().get("portada", {})
    variantes = portada.get("variantes") or []
    validas = [v for v in variantes if v.get("id") and v.get("canva_design_id")]
    if validas:
        return validas
    return [{
        "id": "portada-1",
        "canva_design_id": portada.get("canva_design_id", ""),
        "banda_titulo": list(BANDA_TITULO),
        "banda_marca": None,
    }]


def _recorte(color, banda):
    """Recorta la zona que ocupa un elemento, en fracciones del lado.

    Admite dos formas: [arriba, abajo] (franja de ancho completo, que es como
    se medía antes) o [izquierda, derecha, arriba, abajo] (la caja real del
    elemento, que es lo que distingue una marca de agua centrada de una en la
    esquina cuando caen a la misma altura).
    """
    if len(banda) == 2:
        x0, x1, y0, y1 = 0.0, 1.0, banda[0], banda[1]
    elif len(banda) == 4:
        x0, x1, y0, y1 = banda
    else:
        raise ValueError(
            "Una banda es [arriba, abajo] o [izquierda, derecha, arriba, abajo]."
        )
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError("Las fracciones de una banda deben ir en orden dentro de [0, 1].")
    ancho, alto = color.size
    return color.crop(
        (int(ancho * x0), int(alto * y0), int(ancho * x1), int(alto * y1))
    )


def _fondo(franja_color) -> tuple:
    """Color medio de la franja y sus dos bloques extremos (claro y oscuro)."""
    from PIL import ImageStat

    medio = tuple(int(round(v)) for v in ImageStat.Stat(franja_color).mean[:3])
    claro, oscuro = _extremos(franja_color)
    return medio, claro, oscuro


def _usos_color() -> dict[str, int]:
    usos: dict[str, int] = {}
    for indice, entrada in enumerate(_historial()):
        usado = (entrada.get("portada") or {}).get("color")
        if usado:
            usos[usado.upper()] = indice
    return usos


def _candidatos_color(franja_color, usos: dict[str, int]) -> tuple[list[dict], list[dict], tuple]:
    """Evalúa la paleta contra una franja: (todos, viables, fondo medido)."""
    medio, claro, oscuro = _fondo(franja_color)
    candidatos = []
    for entrada_color in _paleta_titulo():
        rgb = _hex_a_rgb(entrada_color["hex"])
        contraste = _contraste(rgb, medio)
        peor = min(_contraste(rgb, claro), _contraste(rgb, oscuro))
        hex_norm = entrada_color["hex"].upper()
        candidatos.append({
            "id": entrada_color.get("id", hex_norm),
            "hex": hex_norm,
            "familia": entrada_color.get("familia", ""),
            "nota": entrada_color.get("nota", ""),
            "contraste": round(contraste, 2),
            "contraste_peor_zona": round(peor, 2),
            "viable": contraste >= CONTRASTE_MINIMO,
            "arriesgado": peor < CONTRASTE_EXTREMO_MINIMO,
            "ultimo_uso": ("nunca" if hex_norm not in usos
                           else f"post nº {usos[hex_norm] + 1}"),
        })
    viables = [c for c in candidatos if c["viable"] and not c["arriesgado"]]
    if not viables:
        viables = [c for c in candidatos if c["viable"]]
    return candidatos, viables, (medio, claro, oscuro)


def _rotar_color(viables: list[dict], usos: dict[str, int]) -> tuple[dict | None, str]:
    if not viables:
        return None, ""
    nunca = [c for c in viables if c["ultimo_uso"] == "nunca"]
    if nunca:
        return random.choice(nunca), "contrasta de sobra y no se ha usado nunca"
    return (min(viables, key=lambda c: usos[c["hex"]]),
            "contrasta de sobra y es el que lleva más posts sin usarse")


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
            "por_defecto": p["id"] == _plantilla_por_defecto(),
            "desactivada": bool(p.get("desactivada")),
            **({"motivo_desactivada": p["motivo_desactivada"]}
               if p.get("motivo_desactivada") else {}),
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

    Salvo que el usuario pida otra cosa explícitamente, la plantilla es la
    marcada como `plantilla_por_defecto` en el catálogo. Las plantillas
    desactivadas se rechazan aquí: es preferencia del usuario, no del modelo.
    """
    p = _buscar(plantilla_id)

    if p.get("desactivada"):
        raise ValueError(
            f"La plantilla '{plantilla_id}' está desactivada por decisión del "
            f"usuario: {p.get('motivo_desactivada', 'sin motivo anotado')} "
            f"Usa '{_plantilla_por_defecto()}' en su lugar."
        )

    max_paginas = p.get("max_paginas")
    minimo = p.get("min_paginas") or min(MIN_SLIDES, max_paginas or MIN_SLIDES)
    if numero_slides < minimo:
        raise ValueError(
            f"'{plantilla_id}' pide al menos {minimo} slides por post (has pedido "
            f"{numero_slides}). Un post más corto se lee en dos segundos y no "
            "compensa el scroll."
        )
    if max_paginas and numero_slides > max_paginas:
        raise ValueError(
            f"'{plantilla_id}' admite un máximo de {max_paginas} slides por post "
            f"(has pedido {numero_slides}). Reduce el número o amplía las páginas "
            "de la plantilla maestra en Canva."
        )

    # Antimonotonía: si los últimos posts seguidos llevan todos el mismo número
    # de slides, ese número queda vetado. Es la regla que rompe la inercia del
    # "siempre 6 palabras" — la decide el código, no el criterio del modelo.
    ultimos = _numeros_recientes(plantilla_id, COOLDOWN_NUMEROS)
    if (
        len(ultimos) == COOLDOWN_NUMEROS
        and len(set(ultimos)) == 1
        and ultimos[0] == numero_slides
    ):
        raise ValueError(
            f"Los últimos {COOLDOWN_NUMEROS} posts de '{plantilla_id}' llevan ya "
            f"{numero_slides} slides. Elige otro número entre {minimo} y "
            f"{max_paginas or minimo} (planificar_post te dice cuál toca) para que "
            "la cuenta no salga siempre igual de larga."
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
        "numeros_recientes": ultimos,
        "angulos_recientes": angulos_recientes(),
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
    `color` es el hex del título; de rotarlo ya se encarga elegir_color_titulo.
    """
    entradas = [h for h in _historial() if h.get("portada")]
    recientes = entradas[-cooldown:] if cooldown > 0 else []
    return [
        {
            "titulo": e["portada"].get("titulo", ""),
            "imagen": e["portada"].get("imagen", ""),
            "origen": e["portada"].get("origen", ""),
            "color": e["portada"].get("color", ""),
            "escena": e["portada"].get("escena", ""),
            "variante": e["portada"].get("variante", ""),
        }
        for e in reversed(recientes)
    ]


@mcp.tool()
def escenas_recientes(cooldown: int = COOLDOWN_ESCENAS) -> list[str]:
    """Escenas de portada usadas en los últimos `cooldown` posts, de más
    reciente a más antigua.

    La escena es el tipo de foto en dos o tres palabras: `museo-porcelana`,
    `callejon-farolillos`, `skyline-nocturno`, `puesto-de-fruta`... Consúltalo
    ANTES de escribir el prompt de la portada y elige una que no aparezca:
    repetir escena es lo que más canta en la cuadrícula del perfil, mucho más
    que repetir una palabra. Fuera de esta ventana la escena vuelve a estar
    disponible — el usuario quiere que se repitan, pero pasado un tiempo
    prudencial (2026-08-31), y 30 posts es un mes largo de publicación diaria.
    """
    entradas = [h for h in _historial() if (h.get("portada") or {}).get("escena")]
    recientes = entradas[-cooldown:] if cooldown > 0 else []
    return [e["portada"]["escena"] for e in reversed(recientes)]


@mcp.tool()
def angulos_recientes(cooldown: int = COOLDOWN_ANGULOS) -> list[str]:
    """Ángulos (tipo de post, no tema) de los últimos posts, el más nuevo primero.

    Un ángulo es la forma de agrupar las palabras: un campo semántico, una
    categoría gramatical, una situación, una tendencia... No repitas ninguno
    de los que salgan aquí: es lo que evita que la cuenta sea siempre
    "N palabras sobre <cosa>".
    """
    salida: list[str] = []
    for entrada in reversed(_historial()):
        angulo = entrada.get("angulo")
        if angulo and angulo not in salida:
            salida.append(angulo)
        if len(salida) >= cooldown:
            break
    return salida


@mcp.tool()
def planificar_post(plantilla_id: str | None = None) -> dict:
    """Decide QUÉ FORMA tiene el post de hoy antes de inventar el contenido:
    cuántas slides lleva y desde qué ángulo se agrupan las palabras.

    Las dos decisiones son rotación, no criterio: gana la opción que lleve más
    posts sin usarse (entre las nunca usadas, una al azar). Es lo que impide
    que todos los posts acaben siendo "6 palabras de un tema", que es a lo que
    tiende el modelo si nadie se lo dice.

    Lo que devuelve es una propuesta con fundamento, no una orden: si el tema
    que se te ocurre pide claramente otro número (hay 5 palabras buenas y la
    sexta es de relleno), ajústalo dentro del rango. Lo que no puedes es
    repetir el número que ya llevan los últimos posts seguidos —
    preparar_encargo lo rechaza.
    """
    plantilla_id = plantilla_id or _plantilla_por_defecto()
    p = _buscar(plantilla_id)

    max_paginas = p.get("max_paginas") or MIN_SLIDES
    minimo = p.get("min_paginas") or min(MIN_SLIDES, max_paginas)
    candidatos = list(range(minimo, max_paginas + 1))

    ultimos = _numeros_recientes(plantilla_id, COOLDOWN_NUMEROS)
    vetado = (
        ultimos[0]
        if len(ultimos) == COOLDOWN_NUMEROS and len(set(ultimos)) == 1
        else None
    )
    if vetado is not None and len(candidatos) > 1:
        candidatos = [n for n in candidatos if n != vetado]

    ultimo_uso: dict[int, int] = {}
    for indice, entrada in enumerate(_historial()):
        if entrada.get("plantilla_id") == plantilla_id:
            ultimo_uso[len(entrada.get("slides", []))] = indice
    nunca = [n for n in candidatos if n not in ultimo_uso]
    if nunca:
        sugerido = random.choice(nunca)
        motivo_n = "no se ha usado nunca ese número de slides"
    else:
        sugerido = min(candidatos, key=lambda n: ultimo_uso[n])
        motivo_n = "es el número que lleva más posts sin usarse"

    familias = _angulos()
    recientes = angulos_recientes()
    libres = [a for a in familias if a["id"] not in recientes] or familias
    ultimo_uso_a: dict[str, int] = {}
    for indice, entrada in enumerate(_historial()):
        if entrada.get("angulo"):
            ultimo_uso_a[entrada["angulo"]] = indice
    nunca_a = [a for a in libres if a["id"] not in ultimo_uso_a]
    if nunca_a:
        angulo = random.choice(nunca_a)
        motivo_a = "no se ha usado nunca"
    else:
        angulo = min(libres, key=lambda a: ultimo_uso_a[a["id"]])
        motivo_a = "es el que lleva más posts sin usarse"

    return {
        "plantilla_id": plantilla_id,
        "numero_slides": {
            "sugerido": sugerido,
            "minimo": minimo,
            "maximo": max_paginas,
            "motivo": motivo_n,
            "recientes": ultimos,
            "vetado": vetado,
        },
        "angulo": {
            "elegido": angulo["id"],
            "descripcion": angulo.get("descripcion", ""),
            "ejemplos": angulo.get("ejemplos", []),
            "motivo": motivo_a,
            "recientes": recientes,
        },
        "otros_angulos": [
            {"id": a["id"], "descripcion": a.get("descripcion", "")}
            for a in familias
            if a["id"] != angulo["id"]
        ],
        "siguiente_paso": (
            "Inventa un tema concreto que encaje en ese ángulo (y que no esté en "
            "temas_publicados), y llama a preparar_encargo(plantilla_id, tema, "
            "numero_slides). Al registrar, pasa angulo=<el id> o la rotación no "
            "aprende."
        ),
    }


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
def preparar_para_cola(carpeta_post: str, max_lado: int = 1080,
                       calidad: int = 90) -> dict:
    """Convierte las imágenes de un post a lo que aceptan Instagram y TikTok,
    dejándolas listas en `<carpeta_post>/_cola/` para encolarlas.

    Regla dura en código, no criterio del modelo: Instagram **solo admite
    JPEG** (nada de PNG) y TikTok admite JPEG/WebP con un máximo de 1080p y
    20 MB por imagen. Los PNG de 2048 px que exporta Canva fallarían en
    ambas, así que aquí se convierten a JPEG y se reescalan a `max_lado`.

    Los originales no se tocan: el PNG a máxima calidad sigue en la carpeta
    del post como archivo. `_cola/` es solo la copia lista para publicar
    (mucho más ligera, que además viaja antes por rsync).
    """
    from PIL import Image

    carpeta = Path(carpeta_post).expanduser()
    if not carpeta.is_dir():
        raise ValueError(f"No existe la carpeta del post: {carpeta}")

    destino = carpeta / "_cola"
    destino.mkdir(exist_ok=True)

    extensiones = {".png", ".jpg", ".jpeg", ".webp"}
    originales = sorted(p for p in carpeta.iterdir()
                        if p.suffix.lower() in extensiones and p.is_file())
    if not originales:
        raise ValueError(f"No hay imágenes en {carpeta}.")

    preparadas, avisos = [], []
    for original in originales:
        salida = destino / f"{original.stem}.jpg"
        with Image.open(original) as img:
            img = img.convert("RGB")  # JPEG no admite transparencia
            if max(img.size) > max_lado:
                proporcion = max_lado / max(img.size)
                nuevo = (round(img.width * proporcion),
                         round(img.height * proporcion))
                img = img.resize(nuevo, Image.LANCZOS)
            img.save(salida, "JPEG", quality=calidad, optimize=True)
        tamano_mb = round(salida.stat().st_size / 1_048_576, 2)
        if tamano_mb > 20:
            avisos.append(f"{salida.name} pesa {tamano_mb} MB: TikTok admite "
                          "20 MB como máximo. Baja `calidad`.")
        preparadas.append({"fichero": salida.name, "mb": tamano_mb})

    return {
        "carpeta_cola": str(destino),
        "imagenes": preparadas,
        "total": len(preparadas),
        "avisos": avisos,
        "siguiente_paso": ("escribe meta.json dentro de esta carpeta _cola/ "
                           "(con `imagenes` nombrando estos .jpg) y encola "
                           "ESTA carpeta, no la del post."),
    }


@mcp.tool()
def elegir_portada(ruta_imagen: str) -> dict:
    """Con la foto de fondo ya elegida, decide **qué variante de la plantilla de
    portada** usar y **de qué color va el título**, en una sola llamada.

    Las variantes (carpeta de Canva `chinesereads-plantilla-portada`, declaradas
    en plantillas.json → `portada.variantes`) son el mismo diseño con el título
    y la marca de agua en sitios distintos. Cuál queda mejor no depende del
    gusto sino de la foto: en una con el cielo despejado arriba y montaña
    abajo, la variante que pone el título arriba se lee y la que lo pone en
    medio no. Así que se mide, no se elige a ojo.

    Para cada variante se calcula:

    - el contraste de cada color de la paleta contra su franja de título (y de
      sus zonas extremas, que es donde un color plano se rompe);
    - el contraste de la marca de agua —que va fija en rojo de marca y **no se
      puede recolorear**— contra la franja donde caiga en esa variante. Esta es
      la única palanca que existe para que el logo no se pierda.

    Gana una variante que tenga al menos un color de título viable (3:1) y la
    marca legible; entre las que cumplen, la que lleve más posts sin usarse,
    para que las cinco roten. Después se elige el color con el mismo criterio.

    Registra las dos cosas en `registrar_publicacion`: `portada['variante']` y
    `portada['color']`. Sin eso las dos rotaciones se quedan paradas.
    """
    from PIL import Image, ImageStat

    ruta = Path(ruta_imagen).expanduser()
    if not ruta.exists():
        raise ValueError(f"No existe el fichero de imagen: {ruta}")

    variantes = _variantes_portada()
    usos_color = _usos_color()
    usos_variante: dict[str, int] = {}
    for indice, entrada in enumerate(_historial()):
        usada = (entrada.get("portada") or {}).get("variante")
        if usada:
            usos_variante[usada] = indice

    rgb_marca = _hex_a_rgb(MARCA_AGUA_HEX)
    informes = []
    with Image.open(ruta) as img:
        color = img.convert("RGB")
        saturacion = round(
            ImageStat.Stat(color.convert("HSV").getchannel("S")).mean[0] / 255, 3
        )
        for v in variantes:
            banda_titulo = v.get("banda_titulo") or list(BANDA_TITULO)
            candidatos, viables, _ = _candidatos_color(
                _recorte(color, banda_titulo), usos_color
            )
            banda_marca = v.get("banda_marca")
            if banda_marca:
                medio_m, claro_m, oscuro_m = _fondo(_recorte(color, banda_marca))
                contraste_marca = round(_contraste(rgb_marca, medio_m), 2)
                peor_marca = round(
                    min(_contraste(rgb_marca, claro_m), _contraste(rgb_marca, oscuro_m)),
                    2,
                )
            else:
                contraste_marca = peor_marca = None
            informes.append({
                "id": v["id"],
                "canva_design_id": v["canva_design_id"],
                "nombre": v.get("nombre", v["id"]),
                "banda_titulo": banda_titulo,
                "banda_marca": banda_marca,
                "contraste_marca": contraste_marca,
                "contraste_marca_peor_zona": peor_marca,
                "marca_legible": (contraste_marca is None
                                  or contraste_marca >= CONTRASTE_MARCA_MINIMO),
                "mejor_contraste_titulo": (
                    max((c["contraste"] for c in candidatos), default=0.0)
                ),
                "colores_viables": [c["hex"] for c in viables],
                "ultimo_uso": ("nunca" if v["id"] not in usos_variante
                               else f"post nº {usos_variante[v['id']] + 1}"),
                "_candidatos": candidatos,
                "_viables": viables,
            })

    aptas = [i for i in informes if i["_viables"] and i["marca_legible"]]
    aviso = ""
    if not aptas:
        aptas = [i for i in informes if i["_viables"]]
        if aptas:
            aviso = ("En ninguna variante contrasta la marca de agua; se elige "
                     "por legibilidad del título. Si el logo se pierde del todo, "
                     "mejor cambiar de foto.")

    elegida = None
    motivo = ""
    if aptas:
        nunca = [i for i in aptas if i["ultimo_uso"] == "nunca"]
        if nunca:
            elegida = max(nunca, key=lambda i: i["contraste_marca"] or 0)
            motivo = ("no se ha usado nunca y es donde mejor caen título y "
                      "marca de agua sobre esta foto")
        else:
            elegida = min(aptas, key=lambda i: usos_variante[i["id"]])
            motivo = "es la que lleva más posts sin usarse de las que aguantan esta foto"

    elegido_color, motivo_color = (
        _rotar_color(elegida["_viables"], usos_color) if elegida else (None, "")
    )

    for i in informes:
        i["_candidatos"].sort(key=lambda c: c["contraste"], reverse=True)
        i["candidatos_titulo"] = i.pop("_candidatos")
        i.pop("_viables")

    return {
        "elegida": (
            {k: elegida[k] for k in ("id", "canva_design_id", "nombre",
                                     "banda_titulo", "banda_marca",
                                     "contraste_marca")}
            if elegida else None
        ),
        "motivo": motivo,
        "color": elegido_color,
        "motivo_color": motivo_color,
        "saturacion": saturacion,
        "casi_monocroma": saturacion < SATURACION_MINIMA,
        "variantes": informes,
        "ninguna_viable": elegida is None,
        "aviso": aviso,
        "siguiente_paso": (
            (("AVISO: la foto es casi monocroma (saturación "
              f"{saturacion}): legible, pero en el feed se verá en blanco y "
              "negro. Repite el prompt con una escena clara pero CON color "
              "salvo que el blanco y negro sea deliberado. ")
             if saturacion < SATURACION_MINIMA else "")
            + "copy-design del 'canva_design_id' de la variante elegida, "
              "update_fill con la foto, replace_text del título y format_text "
              "con el hex de 'color'. Al registrar, pasa portada['variante'] y "
              "portada['color'] o las dos rotaciones se quedan paradas."
            if elegida else
            "Ninguna variante consigue un título legible sobre esta foto: el "
            "fondo está demasiado revuelto en todas las franjas. Cambia de "
            "imagen (antes un descarte ya pagado que una generación nueva)."
        ),
    }


@mcp.tool()
def elegir_color_titulo(ruta_imagen: str, banda: list[float] | None = None) -> dict:
    """Mide la foto de portada y decide **de qué color va el título**, entre
    los colores de marca declarados en plantillas.json (`portada` →
    `colores_titulo`).

    Sustituye a mirar la imagen a ojo. Dos reglas duras, las dos en código:

    1. **Legibilidad primero.** El contraste se calcula con la fórmula de la
       WCAG entre cada color de la paleta y el fondo real de la *franja donde
       cae el título* (no la media de toda la foto: una foto oscura con nubes
       claras justo detrás del texto engañaba a la media). Solo se consideran
       viables los colores que llegan a 3:1, el mínimo para texto grande.
    2. **Variedad después.** Entre los viables gana el que lleve más posts sin
       usarse (o uno al azar entre los que no se han usado nunca), leyendo
       `portada.color` del historial. Así el feed no sale siempre igual sin
       que ningún post pierda legibilidad.

    Recolorear es **gratis e instantáneo** (`format_text` en la transacción de
    edición de Canva) y generar una imagen nueva cuesta pollen: si el título
    no se lee, esto es lo primero que hay que probar. Solo si
    `ninguno_viable` es true la foto no tiene salida y toca cambiarla.

    `banda` permite acotar la franja vertical analizada como fracciones de la
    altura ([0.27, 0.60] por defecto, que es donde cae el título en la
    plantilla de portada).
    """
    from PIL import Image, ImageStat

    ruta = Path(ruta_imagen).expanduser()
    if not ruta.exists():
        raise ValueError(f"No existe el fichero de imagen: {ruta}")

    desde, hasta = BANDA_TITULO if banda is None else (banda[0], banda[1])
    if not 0 <= desde < hasta <= 1:
        raise ValueError("banda debe ser [desde, hasta] con 0 <= desde < hasta <= 1.")

    with Image.open(ruta) as img:
        color = img.convert("RGB")
        gris = color.convert("L")
        ancho, alto = gris.size
        tercio = alto // 3
        caja = (0, int(alto * desde), ancho, int(alto * hasta))
        franja_color = color.crop(caja)
        franja_gris = gris.crop(caja)

        def _media_gris(recorte) -> float:
            return round(ImageStat.Stat(recorte).mean[0], 1)

        luminancia = {
            "global": _media_gris(gris),
            "tercio_superior": _media_gris(gris.crop((0, 0, ancho, tercio))),
            "tercio_central": _media_gris(gris.crop((0, tercio, ancho, 2 * tercio))),
            "tercio_inferior": _media_gris(gris.crop((0, 2 * tercio, ancho, alto))),
            "banda_titulo": _media_gris(franja_gris),
        }

        # Saturación media de la foto entera: una portada legible pero gris
        # (niebla, nieve, cielo blanco) se ve en blanco y negro en el feed.
        saturacion = round(
            ImageStat.Stat(color.convert("HSV").getchannel("S")).mean[0] / 255, 3
        )

        usos = _usos_color()
        candidatos, viables, (medio, claro, oscuro) = _candidatos_color(
            franja_color, usos
        )

    elegido, motivo = _rotar_color(viables, usos)

    candidatos.sort(key=lambda c: c["contraste"], reverse=True)
    return {
        "luminancia": luminancia,
        "fondo_banda": {
            "rgb": list(medio),
            "hex": _rgb_a_hex(medio),
            "zona_mas_clara": _rgb_a_hex(claro),
            "zona_mas_oscura": _rgb_a_hex(oscuro),
        },
        "banda_analizada": [desde, hasta],
        "saturacion": saturacion,
        "casi_monocroma": saturacion < SATURACION_MINIMA,
        "elegido": elegido,
        "motivo": motivo,
        "candidatos": candidatos,
        "ninguno_viable": elegido is None,
        "siguiente_paso": (
            ("AVISO: la foto es casi monocroma (saturación "
             f"{saturacion}): legible, pero en el feed se verá en blanco y "
             "negro. Luminoso no es lo mismo que gris — repite el prompt con "
             "una escena clara pero CON color (madera, verde, textiles, "
             "tejados, luz cálida) salvo que el blanco y negro sea "
             "deliberado. " if saturacion < SATURACION_MINIMA else "")
            + "Aplica el hex de 'elegido' al título con format_text en la "
            "misma transacción de edición, y pásalo como portada['color'] en "
            "registrar_publicacion (sin eso la rotación de colores no avanza)."
            if elegido else
            "Ningún color de la paleta llega a 3:1 sobre esa franja: la foto "
            "tiene el fondo demasiado revuelto justo donde va el título. Aquí "
            "sí toca cambiar de imagen (otro descarte ya pagado antes que una "
            "generación nueva)."
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
    angulo: str = "",
) -> dict:
    """Guarda en el historial un post completo ya creado en Canva (todas sus
    slides de una vez, en una sola llamada por post).

    Llama a esto solo DESPUÉS de que el diseño exista de verdad, con la URL que
    devuelva Canva. Cada elemento de `slides` es un dict con "identificador"
    (lo que identifica esa slide, p. ej. la palabra) y "contenido" (el dict de
    huecos de texto usado). Si el post lleva portada, pásala también:
    {"titulo": "...", "imagen": "<nombre del asset o prompt+seed de IA>",
    "origen": "ia" | "galeria" | "manual", "color": "#RRGGBB",
    "escena": "museo-porcelana", "variante": "portada-3"} — es lo que alimenta el cooldown de
    portadas_recientes, la rotación de colores de elegir_color_titulo (sin
    `color`, el título tenderá a salir siempre igual) y el cooldown de escenas
    de escenas_recientes (sin `escena`, las portadas se repetirán de tipo) y la
    rotación de variantes de elegir_portada (sin `variante`, siempre saldrá la
    misma plantilla de portada). Si lleva slide final de cierre, pasa también
    final={"nombre": "<título de la plantilla-final>", "design_id": "..."} —
    es lo que alimenta la rotación de elegir_final. Pasa también `angulo` con
    el id de familia que devolvió planificar_post (`campo-semantico`,
    `categoria-gramatical`, `situacion`...): sin él la rotación de ángulos se
    queda parada y los posts vuelven a ser todos del mismo corte. El historial
    es lo que evita que repitas temas, palabras, fotos de portada, número de
    slides, ángulo y slide final.
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
        if portada.get("color"):
            _hex_a_rgb(portada["color"])  # valida el formato #RRGGBB
            portada["color"] = portada["color"].strip().upper()
        if portada.get("escena"):
            portada["escena"] = _normalizar(portada["escena"]).replace(" ", "-")
        if portada.get("variante"):
            portada["variante"] = portada["variante"].strip()
            conocidas = {v["id"] for v in _variantes_portada()}
            if portada["variante"] not in conocidas:
                raise ValueError(
                    f"portada['variante'] = '{portada['variante']}' no es ninguna "
                    f"de las declaradas en plantillas.json: {sorted(conocidas)}. "
                    "Pasa el 'id' que devolvió elegir_portada."
                )

    if final is not None:
        if not final.get("nombre"):
            raise ValueError("final necesita 'nombre' (el título de la "
                             "plantilla-final usada).")

    avisos: list[str] = []
    if portada is not None and not portada.get("variante"):
        avisos.append(
            "Sin portada['variante']: la rotación de plantillas de portada no "
            "aprende de este post."
        )
    angulo = _normalizar(angulo).replace(" ", "-") if angulo else ""
    if not angulo:
        avisos.append(
            "Sin 'angulo': la rotación de planificar_post no aprende de este post "
            "y los siguientes tenderán a repetir el mismo corte."
        )
    elif angulo not in {a["id"] for a in _angulos()}:
        avisos.append(
            f"El ángulo '{angulo}' no está declarado en plantillas.json "
            f"(angulos_de_post). Se guarda igual, pero no entrará en la rotación: "
            "revisa si es una errata o si toca darlo de alta."
        )

    entrada = {
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plantilla_id": plantilla_id,
        "tema": tema,
        "angulo": angulo,
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

    return {
        "guardado": True,
        "total_posts": len(historial),
        "entrada": entrada,
        "avisos": avisos,
    }


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
