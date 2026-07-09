"""Configuración central: tickers, umbrales y constantes del informe semanal.

No contiene lógica de descarga ni de cálculo — solo datos.
"""

# --------------------------------------------------------------------------
# S1. Panorama de mercado
# --------------------------------------------------------------------------
TICKERS_INDICES = ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX"]

NOMBRES_INDICES = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq Composite",
    "^DJI": "Dow Jones Industrial Average",
    "^RUT": "Russell 2000",
    "^VIX": "VIX",
}

TICKER_SPX = "^GSPC"
TICKER_VIX = "^VIX"

# --------------------------------------------------------------------------
# S2. Rotación sectorial — 11 ETFs sectoriales SPDR
# --------------------------------------------------------------------------
TICKERS_SECTORES = [
    "XLF", "XLC", "XLY", "XLV", "XLI",
    "XLB", "XLP", "XLK", "XLU", "XLE", "XLRE",
]

NOMBRES_SECTORES = {
    "XLF": "Financiero",
    "XLC": "Comunicaciones",
    "XLY": "Consumo discrecional",
    "XLV": "Salud",
    "XLI": "Industrial",
    "XLB": "Materiales",
    "XLP": "Consumo básico",
    "XLK": "Tecnología",
    "XLU": "Utilities",
    "XLE": "Energía",
    "XLRE": "Real Estate",
}

SECTORES_CICLICOS = ["XLF", "XLY", "XLI", "XLB", "XLK", "XLC"]
SECTORES_DEFENSIVOS = ["XLP", "XLU", "XLV", "XLRE"]

# --------------------------------------------------------------------------
# S3. Divisas y macro global
# --------------------------------------------------------------------------
TICKERS_FX = [
    "EURUSD=X", "GBPUSD=X", "JPY=X", "CHF=X", "AUDUSD=X",
    "CAD=X", "CNY=X", "MXN=X", "BRL=X",
]

NOMBRES_FX = {
    "EURUSD=X": "Euro",
    "GBPUSD=X": "Libra esterlina",
    "JPY=X": "Yen japonés",
    "CHF=X": "Franco suizo",
    "AUDUSD=X": "Dólar australiano",
    "CAD=X": "Dólar canadiense",
    "CNY=X": "Yuan chino",
    "MXN=X": "Peso mexicano",
    "BRL=X": "Real brasileño",
}

# Pares cotizados como USD/XXX (una suba del par = XXX se deprecia frente al USD).
# Los demás (EURUSD=X, GBPUSD=X, AUDUSD=X) cotizan XXX/USD (una suba = XXX se aprecia).
FX_INVERSOS = {"JPY=X", "CHF=X", "CAD=X", "CNY=X", "MXN=X", "BRL=X"}

# Índice sintético del dólar: ponderadores contra majors (deben sumar 1.0)
PONDERADORES_USD = {
    "EURUSD=X": 0.40,
    "JPY=X": 0.20,
    "GBPUSD=X": 0.15,
    "CHF=X": 0.10,
    "AUDUSD=X": 0.075,
    "CAD=X": 0.075,
}

TICKERS_MACRO = ["GC=F", "CL=F", "BTC-USD"]

NOMBRES_MACRO = {
    "GC=F": "Oro",
    "CL=F": "WTI",
    "BTC-USD": "Bitcoin",
}

FRED_SERIE_10Y = "DGS10"
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"

# --------------------------------------------------------------------------
# S4. Flujos institucionales vs minoristas (proxies)
# --------------------------------------------------------------------------
TICKERS_FLUJOS = ["RSP", "SPY", "IWM", "SPHB", "SPLV", "HYG", "TLT"]

SPREADS_FLUJOS = [
    ("RSP", "SPY", "Equiponderado vs. cap-ponderado"),
    ("IWM", "SPY", "Small caps vs. large caps"),
    ("SPHB", "SPLV", "Alta beta vs. baja volatilidad"),
    ("HYG", "TLT", "Crédito high-yield vs. Treasuries largos"),
]

TICKER_VOLUMEN_REFERENCIA = "SPY"
SEMANAS_PROMEDIO_VOLUMEN = 4

# --------------------------------------------------------------------------
# S6/S7/S8 (fase 2) — placeholders de configuración
# --------------------------------------------------------------------------
CSV_CONSTITUYENTES = "constituyentes_sp500.csv"
UMBRAL_PLANO = 0.0025  # |var| < 0.25% se considera "plano"
CHUNK_SIZE_CONSTITUYENTES = 100
PERIODO_DESCARGA_CONSTITUYENTES = "18mo"  # >=200 ruedas de historia para EMA200
MIN_CONSTITUYENTES_EFECTIVOS = 50  # piso de confiabilidad para S6/S7/S8
EMA_CORTA = 50
EMA_LARGA = 200
TOP_N_GANADORES_PERDEDORES = 10
BUCKETS_HISTOGRAMA = [
    (-float("inf"), -0.05, "< −5%"),
    (-0.05, -0.02, "−5% a −2%"),
    (-0.02, 0.0, "−2% a 0%"),
    (0.0, 0.02, "0% a +2%"),
    (0.02, 0.05, "+2% a +5%"),
    (0.05, float("inf"), "> +5%"),
]

# --------------------------------------------------------------------------
# S9 (fase 3)
# --------------------------------------------------------------------------
FINNHUB_API_URL_CALENDAR = "https://finnhub.io/api/v1/calendar/earnings"
FINNHUB_RATE_LIMIT_SLEEP = 1.1  # solo relevante si se agregan llamadas por-reporte

# --------------------------------------------------------------------------
# Descarga / robustez
# --------------------------------------------------------------------------
INTENTOS_DESCARGA = 3
BACKOFF_SEGUNDOS = (5, 15, 45)
MIN_SESIONES_SEMANA = 4
PERIODO_DESCARGA_DEFAULT = "3mo"

# Mapeo best-effort a símbolos de Stooq para el fallback (índices/FX/commodities).
# Se usa solo si yfinance devuelve vacío para alguno de estos tickers.
STOOQ_MAP = {
    "^GSPC": "^spx",
    "^IXIC": "^ndq",
    "^DJI": "^dji",
    "^RUT": "^rut",
    "^VIX": "^vix",
    "EURUSD=X": "eurusd",
    "GBPUSD=X": "gbpusd",
    "JPY=X": "usdjpy",
    "CHF=X": "usdchf",
    "AUDUSD=X": "audusd",
    "CAD=X": "usdcad",
    "CNY=X": "usdcny",
    "MXN=X": "usdmxn",
    "BRL=X": "usdbrl",
    "GC=F": "xauusd",
    "CL=F": "cl.f",
}

# --------------------------------------------------------------------------
# Metadatos del informe
# --------------------------------------------------------------------------
TITULO_SITIO = "INFORME SEMANAL DE MERCADO — INTERNACIONAL"
DISCLAIMER = (
    "Informe generado automáticamente con datos públicos. "
    "No constituye recomendación de inversión."
)
URL_BASE = "https://alphainvestment.github.io/Internacional"
