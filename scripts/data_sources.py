"""Descarga de datos de mercado con retry + fallback yfinance -> Stooq.

Expone:
  - descargar(tickers, periodo): dict {ticker: DataFrame}, cacheado en memoria
    por ticker durante la corrida del proceso.
  - descargar_fred_10y(api_key): pd.Series con la Tasa 10Y (serie DGS10).
"""

import io
import sys
import time

import pandas as pd
import requests
import yfinance as yf

import config

_cache = {}


def _log(msg):
    print(f"[data_sources] {msg}", file=sys.stderr)


def _descargar_yfinance(ticker, periodo):
    try:
        df = yf.download(
            ticker, period=periodo, interval="1d", progress=False, auto_adjust=False
        )
    except Exception as e:
        _log(f"yfinance error para {ticker}: {e}")
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _dias_periodo(periodo):
    unidades = {"d": 1, "mo": 30, "y": 365}
    for suf, mult in unidades.items():
        if periodo.endswith(suf):
            try:
                return int(periodo[: -len(suf)]) * mult
            except ValueError:
                continue
    return None


def _descargar_stooq(ticker, periodo):
    simbolo = config.STOOQ_MAP.get(ticker)
    if simbolo is None:
        return None
    url = f"https://stooq.com/q/d/l/?s={simbolo}&i=d"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        _log(f"Stooq error para {ticker} ({simbolo}): {e}")
        return None

    texto = resp.text
    if not texto or "Date,Open" not in texto:
        return None
    try:
        df = pd.read_csv(io.StringIO(texto), parse_dates=["Date"])
    except Exception as e:
        _log(f"Stooq parse error para {ticker}: {e}")
        return None
    if df.empty:
        return None

    df = df.set_index("Date").sort_index()
    dias = _dias_periodo(periodo)
    if dias:
        corte = df.index.max() - pd.Timedelta(days=dias)
        df = df[df.index >= corte]
    return df


def _descargar_un_ticker(ticker, periodo):
    for intento in range(config.INTENTOS_DESCARGA):
        df = _descargar_yfinance(ticker, periodo)
        if df is not None and len(df) >= config.MIN_SESIONES_SEMANA:
            return df
        if intento < config.INTENTOS_DESCARGA - 1:
            espera = config.BACKOFF_SEGUNDOS[min(intento, len(config.BACKOFF_SEGUNDOS) - 1)]
            _log(f"Reintentando {ticker} en {espera}s (intento {intento + 1}/{config.INTENTOS_DESCARGA})")
            time.sleep(espera)

    _log(f"yfinance agotó reintentos para {ticker}; probando fallback Stooq")
    df = _descargar_stooq(ticker, periodo)
    if df is not None and len(df) >= config.MIN_SESIONES_SEMANA:
        return df

    _log(f"No se pudo descargar {ticker} (ni yfinance ni Stooq)")
    return None


def descargar(tickers, periodo=config.PERIODO_DESCARGA_DEFAULT):
    """Descarga precios diarios para una lista de tickers.

    Devuelve dict {ticker: DataFrame}; solo incluye tickers con datos válidos.
    Cachea en memoria — una sola descarga real por ticker por corrida.
    """
    resultado = {}
    for ticker in tickers:
        if ticker in _cache:
            resultado[ticker] = _cache[ticker]
            continue
        df = _descargar_un_ticker(ticker, periodo)
        if df is not None:
            _cache[ticker] = df
            resultado[ticker] = df
    return resultado


def descargar_fred_10y(api_key, periodo_dias=120):
    """Descarga la serie DGS10 (Tasa a 10 años) de FRED. Devuelve pd.Series o None."""
    if not api_key:
        _log("FRED_API_KEY no configurada; se omite la Tasa 10Y")
        return None

    fecha_desde = (pd.Timestamp.today().normalize() - pd.Timedelta(days=periodo_dias)).strftime("%Y-%m-%d")
    params = {
        "series_id": config.FRED_SERIE_10Y,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": fecha_desde,
    }
    for intento in range(config.INTENTOS_DESCARGA):
        try:
            resp = requests.get(config.FRED_API_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            obs = data.get("observations", [])
            serie = pd.Series(
                {pd.Timestamp(o["date"]): float(o["value"]) for o in obs if o["value"] != "."}
            ).sort_index()
            if serie.empty:
                return None
            return serie
        except Exception as e:
            _log(f"FRED error (intento {intento + 1}/{config.INTENTOS_DESCARGA}): {e}")
            if intento < config.INTENTOS_DESCARGA - 1:
                time.sleep(config.BACKOFF_SEGUNDOS[min(intento, len(config.BACKOFF_SEGUNDOS) - 1)])
    return None


def limpiar_cache():
    _cache.clear()
