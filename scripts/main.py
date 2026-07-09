"""Orquestador del informe semanal: descarga -> cálculo -> narrativa -> render.

Uso: python scripts/main.py [--referencia YYYY-MM-DD]

Exit code 0: informe publicado. Exit code 1: núcleo (S1/S3) sin datos
válidos, o HTML incompleto — no se debe publicar (ver spec, "Qué NO hacer").
"""

import argparse
import json
import os
import sys

import pandas as pd

import calculos
import config
import data_sources
import narrativa
import render

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INFORMES_DIR = os.path.join(RAIZ, "informes")
MANIFEST_PATH = os.path.join(INFORMES_DIR, "manifest.json")
INDEX_PATH = os.path.join(RAIZ, "index.html")


def _log(msg):
    print(f"[main] {msg}", file=sys.stderr)


def _tickers_necesarios():
    return list(dict.fromkeys(
        config.TICKERS_INDICES
        + config.TICKERS_SECTORES
        + config.TICKERS_FX
        + config.TICKERS_MACRO
        + config.TICKERS_FLUJOS
    ))


def _cargar_manifest():
    if not os.path.exists(MANIFEST_PATH):
        return []
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _guardar_manifest(informes):
    os.makedirs(INFORMES_DIR, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(informes, f, ensure_ascii=False, indent=2)


def main(referencia=None):
    _log("Descargando datos de mercado...")
    datos = data_sources.descargar(_tickers_necesarios())
    fred_10y = data_sources.descargar_fred_10y(os.environ.get("FRED_API_KEY"))

    _log("Calculando métricas (S1-S4)...")
    resultado = calculos.calcular_todo(datos, fred_10y, referencia)

    s1, s3 = resultado["s1"], resultado["s3"]
    if not s1.get("disponible") or not s3.get("disponible"):
        _log("ERROR: núcleo (S1 y/o S3) sin datos válidos esta semana. Abortando sin publicar.")
        return 1

    _log("Generando narrativa por reglas...")
    textos = narrativa.generar_informe(resultado)

    semana = resultado["semana"]
    fecha_viernes = semana["viernes"].date()
    nombre_archivo = f"{fecha_viernes.isoformat()}.html"
    salida_informe = os.path.join(INFORMES_DIR, nombre_archivo)

    contexto = {
        "semana": semana,
        "fecha_generacion": calculos.hoy(),
        "titulo": textos["titulo"],
        "bajada": textos["bajada"],
        "balance": textos["balance"],
        "resumen": textos["resumen"],
        "claves": textos["claves"],
        "lectura_panorama": textos["lectura_panorama"],
        "lectura_sectores": textos["lectura_sectores"],
        "lectura_macro": textos["lectura_macro"],
        "lectura_flujos": textos["lectura_flujos"],
        "s1": s1,
        "s2": resultado["s2"],
        "s3": s3,
        "s4": resultado["s4"],
    }

    _log(f"Renderizando {salida_informe}...")
    html = render.render_informe(contexto, salida_informe)
    if not html or len(html) < 500:
        _log("ERROR: HTML generado vacío o incompleto. Abortando sin publicar.")
        return 1

    manifest = _cargar_manifest()
    manifest = [m for m in manifest if m["archivo"] != nombre_archivo]
    manifest.append({
        "fecha": fecha_viernes.isoformat(),
        "lunes": semana["lunes"].date().isoformat(),
        "viernes": fecha_viernes.isoformat(),
        "titulo": textos["titulo"],
        "archivo": nombre_archivo,
    })
    manifest.sort(key=lambda m: m["fecha"], reverse=True)
    _guardar_manifest(manifest)

    release_info = {
        "tag": f"internacional-{fecha_viernes.isoformat()}",
        "titulo": textos["titulo"],
        "claves": textos["claves"],
        "url": f"{config.URL_BASE}/informes/{nombre_archivo}",
        "lunes": semana["lunes"].date().isoformat(),
        "viernes": fecha_viernes.isoformat(),
    }
    with open(os.path.join(INFORMES_DIR, "ultimo_release.json"), "w", encoding="utf-8") as f:
        json.dump(release_info, f, ensure_ascii=False, indent=2)

    informes_index = [
        {
            "lunes": pd.Timestamp(m["lunes"]),
            "viernes": pd.Timestamp(m["viernes"]),
            "titulo": m["titulo"],
            "archivo": m["archivo"],
        }
        for m in manifest
    ]
    _log("Actualizando index.html...")
    render.render_index(informes_index, INDEX_PATH)

    _log(f"OK. Informe publicado en {salida_informe}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera el informe semanal internacional.")
    parser.add_argument(
        "--referencia",
        help="Fecha de referencia ('hoy') en formato YYYY-MM-DD, para testear semanas pasadas.",
        default=None,
    )
    args = parser.parse_args()
    sys.exit(main(referencia=args.referencia))
