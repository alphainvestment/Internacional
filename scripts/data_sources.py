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


def _descargar_chunk_yfinance(tickers_chunk, periodo):
    try:
        df = yf.download(
            tickers_chunk,
            period=periodo,
            interval="1d",
            group_by="ticker",
            progress=False,
            auto_adjust=False,
            threads=True,
        )
    except Exception as e:
        _log(f"yfinance error en chunk ({len(tickers_chunk)} tickers): {e}")
        return None
    if df is None or df.empty:
        return None
    return df


def _separar_chunk(df, tickers_chunk):
    """Divide el DataFrame multi-ticker de yf.download() en dict {ticker: DataFrame}."""
    resultado = {}
    if isinstance(df.columns, pd.MultiIndex):
        nivel0 = set(df.columns.get_level_values(0))
        for ticker in tickers_chunk:
            if ticker not in nivel0:
                continue
            sub = df[ticker].dropna(how="all")
            if not sub.empty:
                resultado[ticker] = sub
    elif len(tickers_chunk) == 1:
        sub = df.dropna(how="all")
        if not sub.empty:
            resultado[tickers_chunk[0]] = sub
    return resultado


def descargar_masivo(tickers, periodo=config.PERIODO_DESCARGA_DEFAULT, chunk_size=None):
    """Descarga en chunks (yf.download con varios tickers por llamada), pensada
    para listas grandes (~500 componentes del S&P 500, fase 2). Retry con
    backoff a nivel de chunk; tolerante a tickers individuales faltantes
    dentro de un chunk exitoso.

    Devuelve (datos: dict {ticker: DataFrame}, fallidos: list[str]).
    """
    chunk_size = chunk_size or config.CHUNK_SIZE_CONSTITUYENTES
    datos = {}
    fallidos = []

    chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
    for n, chunk in enumerate(chunks, start=1):
        _log(f"Descargando chunk {n}/{len(chunks)} ({len(chunk)} tickers)...")
        df = None
        for intento in range(config.INTENTOS_DESCARGA):
            df = _descargar_chunk_yfinance(chunk, periodo)
            if df is not None and not df.empty:
                break
            if intento < config.INTENTOS_DESCARGA - 1:
                espera = config.BACKOFF_SEGUNDOS[min(intento, len(config.BACKOFF_SEGUNDOS) - 1)]
                _log(f"Reintentando chunk {n} en {espera}s (intento {intento + 1}/{config.INTENTOS_DESCARGA})")
                time.sleep(espera)

        if df is None or df.empty:
            _log(f"Chunk {n} falló tras {config.INTENTOS_DESCARGA} intentos; se excluyen {len(chunk)} tickers.")
            fallidos.extend(chunk)
            continue

        separados = _separar_chunk(df, chunk)
        for ticker in chunk:
            sub = separados.get(ticker)
            if sub is not None and len(sub) >= config.MIN_SESIONES_SEMANA:
                datos[ticker] = sub
            else:
                fallidos.append(ticker)

    _log(f"Descarga masiva: {len(datos)} de {len(tickers)} tickers efectivos ({len(fallidos)} excluidos).")
    return datos, fallidos


def descargar_earnings_finnhub(api_key, fecha_desde, fecha_hasta):
    """Descarga el calendario de earnings de Finnhub para [fecha_desde, fecha_hasta]
    (strings YYYY-MM-DD, inclusive). Un único call cubre toda la semana --
    el endpoint de calendario no requiere un call por ticker, así que el
    rate limit free (60/min) sobra sin necesidad de sleep entre calls.

    Devuelve la lista cruda de reportes (dicts de Finnhub), o None si la
    key no está configurada o la descarga falla tras los reintentos.
    """
    if not api_key:
        _log("FINNHUB_API_KEY no configurada; se omite la temporada de resultados (S9)")
        return None

    params = {"from": fecha_desde, "to": fecha_hasta, "token": api_key}
    for intento in range(config.INTENTOS_DESCARGA):
        try:
            resp = requests.get(config.FINNHUB_API_URL_CALENDAR, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get("earningsCalendar", [])
        except Exception as e:
            _log(f"Finnhub error (intento {intento + 1}/{config.INTENTOS_DESCARGA}): {e}")
            if intento < config.INTENTOS_DESCARGA - 1:
                time.sleep(config.BACKOFF_SEGUNDOS[min(intento, len(config.BACKOFF_SEGUNDOS) - 1)])
    return None


def limpiar_cache():
    _cache.clear()
