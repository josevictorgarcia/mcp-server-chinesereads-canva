#!/usr/bin/env python3
"""Publicador automático de posts en Instagram y TikTok.

Script independiente: sin MCP, sin dependencias externas (solo stdlib).
Pensado para correr en el VPS con un cron diario. Lee la cola de posts
(carpetas con las imágenes + un meta.json), publica el más antiguo en las
redes configuradas y lo archiva en publicados/.

Por qué no es un servidor MCP: MCP es la interfaz entre un modelo y sus
herramientas — aquí no hay modelo en el bucle. El cron ejecuta este script
a pelo; la descripción y los hashtags ya vienen decididos en el meta.json
que se generó junto al post.

Uso:
  python3 publicador.py estado              comprueba config, tokens y cola
  python3 publicador.py cola                lista los posts pendientes
  python3 publicador.py publicar            publica el post más antiguo
  python3 publicador.py publicar --dry-run  simula sin publicar nada
  python3 publicador.py publicar --solo instagram   (o --solo tiktok)

Configuración en publicacion_config.json (copiar de
publicacion_config.ejemplo.json y rellenar). Contiene tokens: está en
.gitignore y jamás debe subirse a git. Guía completa: PUBLICACION.md.
"""

import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
COLA = BASE / "cola"
PUBLICADOS = BASE / "publicados"
CONFIG = BASE / "publicacion_config.json"
LOG = BASE / "publicador.log"

IG_GRAPH = "https://graph.instagram.com/v23.0"
IG_REFRESH = "https://graph.instagram.com/refresh_access_token"
TIKTOK_API = "https://open.tiktokapis.com/v2"

# Límites duros de cada plataforma (documentados en PUBLICACION.md).
IG_MAX_IMAGENES = 10
IG_MAX_CAPTION = 2200
TT_MAX_IMAGENES = 35
TT_MAX_TITULO = 90
TT_MAX_DESCRIPCION = 4000

UA = "chinesereads-publicador/1.0"
EXTENSIONES_IMAGEN = (".png", ".jpg", ".jpeg", ".webp")


# ---------------------------------------------------------------- utilidades

def _log(mensaje: str) -> None:
    linea = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {mensaje}"
    print(linea)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass


def _http(url: str, *, metodo: str = "GET", form: dict | None = None,
          json_body: dict | None = None, bearer: str = "",
          timeout: int = 90) -> dict:
    """Petición HTTP que devuelve el JSON de respuesta o lanza RuntimeError
    con el cuerpo del error (las APIs de Meta y TikTok explican ahí qué pasó)."""
    headers = {"User-Agent": UA}
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        metodo = "POST"
    elif json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json; charset=UTF-8"
        metodo = "POST"
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    peticion = urllib.request.Request(url, data=data, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as resp:
            cuerpo = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", errors="replace")[:600]
        raise RuntimeError(f"HTTP {e.code} en {url.split('?')[0]}: {detalle}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Sin respuesta de {url.split('?')[0]}: {e}") from None
    try:
        return json.loads(cuerpo)
    except json.JSONDecodeError:
        raise RuntimeError(f"Respuesta no-JSON de {url.split('?')[0]}: {cuerpo[:300]}")


def cargar_config() -> dict:
    if not CONFIG.exists():
        raise SystemExit(
            "No existe publicacion_config.json. Copia "
            "publicacion_config.ejemplo.json, rellénalo (ver PUBLICACION.md) "
            "y vuelve a intentarlo."
        )
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def guardar_config(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------- la cola

def _cargar_meta(carpeta: Path) -> dict:
    return json.loads((carpeta / "meta.json").read_text(encoding="utf-8"))


def _guardar_meta(carpeta: Path, meta: dict) -> None:
    (carpeta / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _imagenes_del_post(carpeta: Path, meta: dict) -> list[str]:
    """Orden de las imágenes: el que fije meta.json o, si no, alfabético
    (00-portada.png queda primera de forma natural)."""
    if meta.get("imagenes"):
        return list(meta["imagenes"])
    return sorted(p.name for p in carpeta.iterdir()
                  if p.suffix.lower() in EXTENSIONES_IMAGEN)


def posts_en_cola() -> list[Path]:
    """Carpetas de la cola con meta.json, de más antigua a más nueva."""
    if not COLA.is_dir():
        return []
    listos = []
    hoy = datetime.now().strftime("%Y-%m-%d")
    for carpeta in COLA.iterdir():
        if not carpeta.is_dir() or not (carpeta / "meta.json").exists():
            continue
        meta = _cargar_meta(carpeta)
        if meta.get("no_publicar_antes_de") and meta["no_publicar_antes_de"] > hoy:
            continue
        listos.append((meta.get("creado", ""), carpeta.name, carpeta))
    return [c for _, _, c in sorted(listos)]


def _url_publica(cfg: dict, carpeta: Path, nombre: str) -> str:
    base = cfg["base_url_publica"].rstrip("/")
    return f"{base}/{urllib.parse.quote(carpeta.name)}/{urllib.parse.quote(nombre)}"


def _componer_caption(cfg: dict, meta: dict) -> str:
    caption = meta.get("caption", "").strip()
    hashtags = meta.get("hashtags") or cfg.get("hashtags_por_defecto") or []
    if hashtags:
        caption = f"{caption}\n\n{' '.join(hashtags)}".strip()
    return caption


# ----------------------------------------------------------------- Instagram

def ig_refrescar_token(cfg: dict) -> None:
    """Renueva el token de larga duración (caduca a los 60 días; renovable a
    partir de las 24 h de vida). Se renueva si hace más de 7 días del último
    refresco — así nunca se acerca a la caducidad mientras el cron corra."""
    ig = cfg["instagram"]
    ultimo = ig.get("token_refrescado", "")
    if ultimo:
        try:
            hace = _ahora() - datetime.fromisoformat(ultimo)
            if hace < timedelta(days=7):
                return
        except ValueError:
            pass
    try:
        respuesta = _http(f"{IG_REFRESH}?grant_type=ig_refresh_token"
                          f"&access_token={urllib.parse.quote(ig['access_token'])}")
        ig["access_token"] = respuesta["access_token"]
        ig["token_refrescado"] = _ahora().isoformat()
        guardar_config(cfg)
        _log("Instagram: token renovado (60 días más).")
    except RuntimeError as e:
        # Un token de menos de 24 h aún no se puede renovar; no es grave.
        _log(f"Instagram: no se pudo renovar el token ({e}). "
             "Se sigue con el actual.")


def _ig_esperar_contenedor(contenedor_id: str, token: str) -> None:
    for _ in range(24):
        estado = _http(f"{IG_GRAPH}/{contenedor_id}"
                       f"?fields=status_code&access_token={urllib.parse.quote(token)}")
        codigo = estado.get("status_code")
        if codigo == "FINISHED":
            return
        if codigo == "ERROR":
            raise RuntimeError(f"Instagram rechazó el contenedor {contenedor_id}: {estado}")
        time.sleep(5)
    raise RuntimeError(f"Instagram no terminó de procesar {contenedor_id} a tiempo.")


def ig_publicar(cfg: dict, carpeta: Path, meta: dict) -> str:
    """Publica el post como carrusel (o imagen única) y devuelve el id."""
    ig = cfg["instagram"]
    token, usuario = ig["access_token"], ig["user_id"]
    caption = _componer_caption(cfg, meta)[:IG_MAX_CAPTION]
    nombres = _imagenes_del_post(carpeta, meta)
    if len(nombres) > IG_MAX_IMAGENES:
        _log(f"Instagram admite {IG_MAX_IMAGENES} imágenes por carrusel; "
             f"se publican las {IG_MAX_IMAGENES} primeras de {len(nombres)}.")
        nombres = nombres[:IG_MAX_IMAGENES]
    urls = [_url_publica(cfg, carpeta, n) for n in nombres]

    if len(urls) == 1:
        contenedor = _http(f"{IG_GRAPH}/{usuario}/media", form={
            "image_url": urls[0], "caption": caption, "access_token": token})["id"]
        _ig_esperar_contenedor(contenedor, token)
    else:
        hijos = []
        for url in urls:
            hijo = _http(f"{IG_GRAPH}/{usuario}/media", form={
                "image_url": url, "is_carousel_item": "true",
                "access_token": token})["id"]
            hijos.append(hijo)
        for hijo in hijos:
            _ig_esperar_contenedor(hijo, token)
        contenedor = _http(f"{IG_GRAPH}/{usuario}/media", form={
            "media_type": "CAROUSEL", "children": ",".join(hijos),
            "caption": caption, "access_token": token})["id"]
        _ig_esperar_contenedor(contenedor, token)

    publicado = _http(f"{IG_GRAPH}/{usuario}/media_publish", form={
        "creation_id": contenedor, "access_token": token})
    return str(publicado.get("id", ""))


# -------------------------------------------------------------------- TikTok

def tt_refrescar_token(cfg: dict) -> None:
    """El access token de TikTok dura 24 h: se renueva en cada ejecución si
    está caducado o a punto. El refresh token rota — hay que guardar siempre
    el que devuelve la respuesta."""
    tt = cfg["tiktok"]
    caduca = tt.get("access_token_caduca", "")
    if caduca:
        try:
            if datetime.fromisoformat(caduca) - _ahora() > timedelta(minutes=30):
                return
        except ValueError:
            pass
    respuesta = _http(f"{TIKTOK_API}/oauth/token/", form={
        "client_key": tt["client_key"],
        "client_secret": tt["client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": tt["refresh_token"],
    })
    if "access_token" not in respuesta:
        raise RuntimeError(f"TikTok no devolvió access_token: {respuesta}")
    tt["access_token"] = respuesta["access_token"]
    tt["refresh_token"] = respuesta.get("refresh_token", tt["refresh_token"])
    caducidad = _ahora() + timedelta(seconds=int(respuesta.get("expires_in", 86400)))
    tt["access_token_caduca"] = caducidad.isoformat()
    guardar_config(cfg)
    _log("TikTok: access token renovado.")


def tt_publicar(cfg: dict, carpeta: Path, meta: dict) -> str:
    """Publica el post como carrusel de fotos y devuelve el publish_id."""
    tt = cfg["tiktok"]
    token = tt["access_token"]

    # TikTok exige consultar la info del creador antes de publicar.
    creador = _http(f"{TIKTOK_API}/post/publish/creator_info/query/",
                    json_body={}, bearer=token)
    if creador.get("error", {}).get("code") not in ("ok", None):
        raise RuntimeError(f"TikTok creator_info falló: {creador['error']}")
    opciones = creador.get("data", {}).get("privacy_level_options", [])
    privacidad = tt.get("privacy_level", "SELF_ONLY")
    if opciones and privacidad not in opciones:
        _log(f"TikTok no permite privacidad {privacidad} en esta cuenta "
             f"(opciones: {opciones}); se usa SELF_ONLY.")
        privacidad = "SELF_ONLY"

    nombres = _imagenes_del_post(carpeta, meta)[:TT_MAX_IMAGENES]
    urls = [_url_publica(cfg, carpeta, n) for n in nombres]
    caption = _componer_caption(cfg, meta)[:TT_MAX_DESCRIPCION]
    titulo = (meta.get("titulo") or meta.get("tema", ""))[:TT_MAX_TITULO]

    inicio = _http(f"{TIKTOK_API}/post/publish/content/init/", json_body={
        "post_info": {
            "title": titulo,
            "description": caption,
            "privacy_level": privacidad,
            "disable_comment": False,
            "auto_add_music": True,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_cover_index": 0,
            "photo_images": urls,
        },
        "post_mode": "DIRECT_POST",
        "media_type": "PHOTO",
    }, bearer=token)
    if inicio.get("error", {}).get("code") not in ("ok", None):
        raise RuntimeError(f"TikTok rechazó la publicación: {inicio['error']}")
    publish_id = inicio["data"]["publish_id"]

    for _ in range(24):
        estado = _http(f"{TIKTOK_API}/post/publish/status/fetch/",
                       json_body={"publish_id": publish_id}, bearer=token)
        situacion = estado.get("data", {}).get("status", "")
        if situacion == "PUBLISH_COMPLETE":
            return publish_id
        if situacion == "FAILED":
            raise RuntimeError(
                f"TikTok falló: {estado['data'].get('fail_reason', estado)}")
        time.sleep(5)
    _log(f"TikTok sigue procesando {publish_id}; se da por enviado "
         "(comprueba la app).")
    return publish_id


# ------------------------------------------------------------------ comandos

def _redes_configuradas(cfg: dict) -> list[str]:
    redes = []
    if cfg.get("instagram", {}).get("access_token"):
        redes.append("instagram")
    if cfg.get("tiktok", {}).get("refresh_token"):
        redes.append("tiktok")
    return redes


def cmd_estado() -> int:
    cfg = cargar_config()
    redes = _redes_configuradas(cfg)
    print(f"Redes configuradas : {', '.join(redes) or 'ninguna'}")
    print(f"URL pública base   : {cfg.get('base_url_publica', '(sin definir)')}")
    if "instagram" in redes:
        print(f"IG último refresco : {cfg['instagram'].get('token_refrescado', 'nunca')}")
    if "tiktok" in redes:
        print(f"TT token caduca    : {cfg['tiktok'].get('access_token_caduca', '¿?')}")
        print(f"TT privacidad      : {cfg['tiktok'].get('privacy_level', 'SELF_ONLY')}")
    pendientes = posts_en_cola()
    print(f"Posts en cola      : {len(pendientes)}")
    for carpeta in pendientes:
        print(f"  - {carpeta.name}")
    return 0


def cmd_cola() -> int:
    for carpeta in posts_en_cola():
        meta = _cargar_meta(carpeta)
        publicado = ", ".join(meta.get("publicado", {})) or "pendiente"
        print(f"{carpeta.name}  [{publicado}]  "
              f"{len(_imagenes_del_post(carpeta, meta))} imágenes")
    else:
        if not posts_en_cola():
            print("Cola vacía.")
    return 0


def _comprobar_url(url: str) -> str:
    try:
        peticion = urllib.request.Request(url, headers={"User-Agent": UA},
                                          method="HEAD")
        with urllib.request.urlopen(peticion, timeout=20) as resp:
            return f"OK ({resp.status})"
    except Exception as e:  # noqa: BLE001 — es solo diagnóstico
        return f"FALLO: {e}"


def cmd_publicar(dry_run: bool, solo: str) -> int:
    cfg = cargar_config()
    redes = _redes_configuradas(cfg)
    if solo:
        redes = [r for r in redes if r == solo]
    if not redes:
        _log("No hay ninguna red configurada que publicar. Revisa "
             "publicacion_config.json (ver PUBLICACION.md).")
        return 1
    pendientes = posts_en_cola()
    if not pendientes:
        _log("Cola vacía: nada que publicar hoy.")
        return 0

    carpeta = pendientes[0]
    meta = _cargar_meta(carpeta)
    ya = meta.setdefault("publicado", {})
    faltan = [r for r in redes if r not in ya]
    if not faltan:
        _log(f"{carpeta.name} ya estaba publicado en {', '.join(redes)}; "
             "se archiva.")
        _archivar(carpeta)
        return 0

    nombres = _imagenes_del_post(carpeta, meta)
    _log(f"Publicando {carpeta.name} ({len(nombres)} imágenes) en: "
         f"{', '.join(faltan)}")

    if dry_run:
        print(f"Caption:\n{_componer_caption(cfg, meta)}\n")
        primera = _url_publica(cfg, carpeta, nombres[0])
        print(f"Primera URL pública: {primera}")
        print(f"Accesible desde fuera: {_comprobar_url(primera)}")
        print("(dry-run: no se ha publicado nada)")
        return 0

    fallos = 0
    for red in faltan:
        try:
            if red == "instagram":
                ig_refrescar_token(cfg)
                resultado = ig_publicar(cfg, carpeta, meta)
            else:
                tt_refrescar_token(cfg)
                resultado = tt_publicar(cfg, carpeta, meta)
            ya[red] = {"id": resultado, "fecha": _ahora().isoformat()}
            _guardar_meta(carpeta, meta)
            _log(f"{red}: publicado ({resultado}).")
        except RuntimeError as e:
            fallos += 1
            _log(f"{red}: ERROR — {e}")

    if all(r in ya for r in redes):
        _archivar(carpeta)
        _log(f"{carpeta.name} archivado en publicados/.")
    else:
        _log(f"{carpeta.name} se queda en la cola para reintentar "
             "las redes que fallaron.")
    return 1 if fallos else 0


def _archivar(carpeta: Path) -> None:
    PUBLICADOS.mkdir(exist_ok=True)
    shutil.move(str(carpeta), str(PUBLICADOS / carpeta.name))


def main() -> int:
    argumentos = sys.argv[1:]
    if not argumentos or argumentos[0] not in ("estado", "cola", "publicar"):
        print(__doc__)
        return 2
    comando = argumentos[0]
    if comando == "estado":
        return cmd_estado()
    if comando == "cola":
        return cmd_cola()
    dry_run = "--dry-run" in argumentos
    solo = ""
    if "--solo" in argumentos:
        indice = argumentos.index("--solo")
        solo = argumentos[indice + 1] if indice + 1 < len(argumentos) else ""
        if solo not in ("instagram", "tiktok"):
            print("--solo admite: instagram | tiktok")
            return 2
    return cmd_publicar(dry_run, solo)


if __name__ == "__main__":
    raise SystemExit(main())
