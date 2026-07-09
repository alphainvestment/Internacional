"""Script auxiliar (fase 2): regenera constituyentes_sp500.csv scrapeando la
tabla de Wikipedia "List of S&P 500 companies". Se corre manualmente cada
tanto -- el pipeline semanal (main.py) solo LEE el CSV, nunca scrapea.

Uso: python scripts/actualizar_constituyentes.py
"""

import csv
import os
import re
import sys
from html.parser import HTMLParser

import requests

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SALIDA = os.path.join(os.path.dirname(__file__), "constituyentes_sp500.csv")


class _TablaConstituyentes(HTMLParser):
    """Extrae filas de la tabla <table id="constituents"> sin dependencias
    externas (sin lxml/html5lib, para no salirse de las librerías permitidas)."""

    def __init__(self):
        super().__init__()
        self.capturando = False
        self.profundidad_tabla = 0
        self.en_fila = False
        self.en_celda = False
        self.fila_actual = []
        self.texto_celda = []
        self.filas = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table":
            if attrs_dict.get("id") == "constituents":
                self.capturando = True
                self.profundidad_tabla = 1
            elif self.capturando:
                self.profundidad_tabla += 1
        elif self.capturando and tag == "tr":
            self.en_fila = True
            self.fila_actual = []
        elif self.capturando and tag in ("td", "th"):
            self.en_celda = True
            self.texto_celda = []

    def handle_endtag(self, tag):
        if tag == "table" and self.capturando:
            self.profundidad_tabla -= 1
            if self.profundidad_tabla == 0:
                self.capturando = False
        elif self.capturando and tag == "tr" and self.en_fila:
            if self.fila_actual:
                self.filas.append(self.fila_actual)
            self.en_fila = False
        elif self.capturando and tag in ("td", "th") and self.en_celda:
            texto = "".join(self.texto_celda).strip()
            texto = re.sub(r"\[.*?\]", "", texto).strip()
            self.fila_actual.append(texto)
            self.en_celda = False

    def handle_data(self, data):
        if self.capturando and self.en_celda:
            self.texto_celda.append(data)


def _a_ticker_yahoo(simbolo):
    """Wikipedia usa notación con punto (BRK.B); Yahoo Finance usa guion (BRK-B)."""
    return simbolo.strip().replace(".", "-")


def obtener_constituyentes():
    resp = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    parser = _TablaConstituyentes()
    parser.feed(resp.text)

    if not parser.filas:
        raise RuntimeError("No se encontró la tabla 'constituents' en la página de Wikipedia.")

    encabezado = [c.lower() for c in parser.filas[0]]
    idx_ticker = encabezado.index("symbol")
    idx_nombre = encabezado.index("security")
    idx_sector = next(i for i, c in enumerate(encabezado) if c.startswith("gics sector"))

    filas = []
    for fila in parser.filas[1:]:
        if len(fila) <= max(idx_ticker, idx_nombre, idx_sector):
            continue
        ticker = _a_ticker_yahoo(fila[idx_ticker])
        nombre = fila[idx_nombre].strip()
        sector = fila[idx_sector].strip()
        if not ticker:
            continue
        filas.append((ticker, nombre, sector))

    return filas


def main():
    filas = obtener_constituyentes()
    if len(filas) < 400:
        print(f"[actualizar_constituyentes] ERROR: solo se extrajeron {len(filas)} filas, algo salió mal.", file=sys.stderr)
        return 1

    with open(SALIDA, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "nombre", "sector"])
        writer.writerows(filas)

    print(f"[actualizar_constituyentes] OK: {len(filas)} constituyentes escritos en {SALIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
