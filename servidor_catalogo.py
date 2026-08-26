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


@mcp.tool()
def registrar_publicacion(
    plantilla_id: str,
    tema: str,
    slides: list[dict],
    url_diseno: str = "",
    notas: str = "",
    portada: dict | None = None,
) -> dict:
    """Guarda en el historial un post completo ya creado en Canva (todas sus
    slides de una vez, en una sola llamada por post).

    Llama a esto solo DESPUÉS de que el diseño exista de verdad, con la URL que
    devuelva Canva. Cada elemento de `slides` es un dict con "identificador"
    (lo que identifica esa slide, p. ej. la palabra) y "contenido" (el dict de
    huecos de texto usado). Si el post lleva portada, pásala también:
    {"titulo": "...", "imagen": "<nombre del asset o prompt+seed de IA>",
    "origen": "ia" | "galeria" | "manual"} — es lo que alimenta el cooldown de
    portadas_recientes. El historial es lo que evita que repitas temas, palabras
    y fotos de portada.
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
