"""Cálculos por sección (S1-S4) a partir de los datos descargados.

Todas las funciones son puras: reciben el dict {ticker: DataFrame} de
data_sources y devuelven estructuras simples (dict/list) listas para
narrativa.py y render.py. Ninguna función descarga datos.
"""

import numpy as np
import pandas as pd

import config


def hoy():
    return pd.Timestamp.today().normalize()


def serie_cierre(df):
    col = "Close" if "Close" in df.columns else "Adj Close"
    return df[col].dropna()


def determinar_semana(indice_fechas, referencia=None):
    """Determina la semana (lunes a viernes) a reportar.

    No hardcodea feriados: la semana objetivo es la semana calendario
    lunes-viernes más reciente que ya terminó respecto de la fecha de
    referencia ("hoy"); dentro de esa ventana se usan solo las fechas que
    realmente tienen dato, para tolerar feriados de mercado (ej: si el
    viernes fue feriado, la última fecha con precio es el jueves).

    Devuelve (lunes, viernes, fechas_de_la_semana, fecha_cierre_previo).
    """
    ref = pd.Timestamp(referencia or hoy()).normalize()
    lunes_actual = ref - pd.Timedelta(days=ref.weekday())
    if ref.weekday() < 5:  # lunes(0)..viernes(4): la semana en curso no cerró
        lunes_semana = lunes_actual - pd.Timedelta(days=7)
    else:  # sábado/domingo: la semana que acaba de terminar ya cerró
        lunes_semana = lunes_actual
    viernes_semana = lunes_semana + pd.Timedelta(days=4)

    fechas = pd.DatetimeIndex(sorted(set(indice_fechas)))
    fechas_semana = fechas[(fechas >= lunes_semana) & (fechas <= viernes_semana)]
    anteriores = fechas[fechas < lunes_semana]
    fecha_previa = anteriores.max() if len(anteriores) else None

    return lunes_semana, viernes_semana, fechas_semana, fecha_previa


def _variacion_semanal(cierre, fechas_semana, fecha_previa):
    """Devuelve (cierre_final, var_semanal) o (None, None) si faltan datos."""
    if fecha_previa is None or fecha_previa not in cierre.index:
        return None, None
    cierre_semana = cierre.reindex(fechas_semana).dropna()
    if cierre_semana.empty:
        return None, None
    cierre_final = cierre_semana.iloc[-1]
    cierre_prev = cierre.loc[fecha_previa]
    return cierre_final, cierre_final / cierre_prev - 1


def calcular_s1(datos, referencia=None):
    """Panorama de mercado: ^GSPC, ^IXIC, ^DJI, ^RUT, ^VIX."""
    resultado = {"disponible": False}
    df_spx = datos.get(config.TICKER_SPX)
    if df_spx is None:
        return resultado

    cierres_spx = serie_cierre(df_spx)
    lunes, viernes, fechas_semana, fecha_previa = determinar_semana(cierres_spx.index, referencia)

    if len(fechas_semana) < config.MIN_SESIONES_SEMANA or fecha_previa is None:
        return resultado

    indices = {}
    for ticker in config.TICKERS_INDICES:
        df = datos.get(ticker)
        if df is None:
            continue
        cierre = serie_cierre(df)
        if fecha_previa not in cierre.index:
            continue
        cierre_semana = cierre.reindex(fechas_semana).dropna()
        if cierre_semana.empty:
            continue

        cierre_prev = cierre.loc[fecha_previa]
        cierre_final = cierre_semana.iloc[-1]
        var_semanal = cierre_final / cierre_prev - 1

        secuencia = []
        base = cierre_prev
        for fecha, valor in cierre_semana.items():
            secuencia.append({"fecha": fecha, "cierre": float(valor), "var": float(valor / base - 1)})
            base = valor

        mejor = max(secuencia, key=lambda d: d["var"])
        peor = min(secuencia, key=lambda d: d["var"])

        indices[ticker] = {
            "ticker": ticker,
            "nombre": config.NOMBRES_INDICES[ticker],
            "cierre": float(cierre_final),
            "var": float(var_semanal),
            "secuencia": secuencia,
            "mejor_sesion": mejor,
            "peor_sesion": peor,
        }

    if config.TICKER_SPX not in indices:
        return resultado  # sin SPX no hay núcleo

    resultado.update({
        "disponible": True,
        "semana": {"lunes": lunes, "viernes": viernes, "fecha_previa": fecha_previa},
        "indices": indices,
        "spx": indices.get(config.TICKER_SPX),
        "vix": indices.get(config.TICKER_VIX),
    })
    return resultado


def calcular_s2(datos, semana):
    """Rotación sectorial: 11 ETFs SPDR."""
    resultado = {"disponible": False}
    lunes, viernes, fechas_semana, fecha_previa = semana
    if fecha_previa is None:
        return resultado

    sectores = []
    for ticker in config.TICKERS_SECTORES:
        df = datos.get(ticker)
        if df is None:
            continue
        cierre = serie_cierre(df)
        cierre_final, var = _variacion_semanal(cierre, fechas_semana, fecha_previa)
        if var is None:
            continue
        sectores.append({"ticker": ticker, "nombre": config.NOMBRES_SECTORES[ticker], "var": float(var)})

    if len(sectores) < 6:  # menos de la mitad -> sección no confiable esta semana
        return resultado

    sectores.sort(key=lambda s: s["var"], reverse=True)
    max_abs = max(abs(s["var"]) for s in sectores) or 1e-9
    for s in sectores:
        s["barra_pct"] = round(abs(s["var"]) / max_abs * 100, 1)

    positivos = sum(1 for s in sectores if s["var"] > 0)
    var_por_ticker = {s["ticker"]: s["var"] for s in sectores}
    ciclicos = [var_por_ticker[t] for t in config.SECTORES_CICLICOS if t in var_por_ticker]
    defensivos = [var_por_ticker[t] for t in config.SECTORES_DEFENSIVOS if t in var_por_ticker]
    prom_ciclicos = float(np.mean(ciclicos)) if ciclicos else None
    prom_defensivos = float(np.mean(defensivos)) if defensivos else None
    spread_cd = (
        prom_ciclicos - prom_defensivos
        if prom_ciclicos is not None and prom_defensivos is not None
        else None
    )

    resultado.update({
        "disponible": True,
        "sectores": sectores,
        "positivos": positivos,
        "total": len(sectores),
        "mejor": sectores[0],
        "peor": sectores[-1],
        "prom_ciclicos": prom_ciclicos,
        "prom_defensivos": prom_defensivos,
        "spread_ciclicos_defensivos": spread_cd,
    })
    return resultado


def calcular_s3(datos, semana, fred_10y=None):
    """Divisas y macro global: FX, índice sintético del dólar, oro/WTI/BTC, Tasa 10Y."""
    resultado = {"disponible": False}
    lunes, viernes, fechas_semana, fecha_previa = semana
    if fecha_previa is None:
        return resultado

    fx = []
    var_por_ticker = {}
    for ticker in config.TICKERS_FX:
        df = datos.get(ticker)
        if df is None:
            continue
        cierre = serie_cierre(df)
        cierre_final, var_par = _variacion_semanal(cierre, fechas_semana, fecha_previa)
        if var_par is None:
            continue
        var_por_ticker[ticker] = var_par
        # Perspectiva de la divisa: en pares USD/XXX una suba del par implica
        # que XXX se debilitó frente al dólar (hay que invertir el signo).
        var_divisa = -var_par if ticker in config.FX_INVERSOS else var_par
        fx.append({
            "ticker": ticker,
            "nombre": config.NOMBRES_FX[ticker],
            "cierre": float(cierre_final),
            "var_par": float(var_par),
            "var_divisa": float(var_divisa),
        })

    if len(fx) < 5:
        return resultado  # S3 es núcleo: si faltan demasiados pares no es confiable

    num, den = 0.0, 0.0
    for ticker, peso in config.PONDERADORES_USD.items():
        if ticker not in var_por_ticker:
            continue
        var_par = var_por_ticker[ticker]
        fortaleza_usd = var_par if ticker in config.FX_INVERSOS else -var_par
        num += peso * fortaleza_usd
        den += peso
    indice_usd = (num / den) if den > 0 else None

    macro = {}
    for ticker in config.TICKERS_MACRO:
        df = datos.get(ticker)
        if df is None:
            continue
        cierre = serie_cierre(df)
        cierre_final, var = _variacion_semanal(cierre, fechas_semana, fecha_previa)
        if var is None:
            continue
        macro[ticker] = {"nombre": config.NOMBRES_MACRO[ticker], "cierre": float(cierre_final), "var": float(var)}

    tasa_10y = None
    if fred_10y is not None and not fred_10y.empty:
        serie_semana = fred_10y.reindex(fechas_semana).dropna()
        anteriores = fred_10y[fred_10y.index < lunes]
        if not serie_semana.empty and not anteriores.empty:
            nivel_final = float(serie_semana.iloc[-1])
            nivel_previo = float(anteriores.iloc[-1])
            tasa_10y = {
                "nivel": nivel_final,
                "nivel_previo": nivel_previo,
                "var_pb": round((nivel_final - nivel_previo) * 100, 1),
            }

    resultado.update({
        "disponible": True,
        "fx": fx,
        "indice_usd": float(indice_usd) if indice_usd is not None else None,
        "macro": macro,
        "tasa_10y": tasa_10y,
    })
    return resultado


def calcular_s4(datos, semana):
    """Flujos institucionales vs. minoristas (proxies): 4 spreads + volumen relativo."""
    resultado = {"disponible": False}
    lunes, viernes, fechas_semana, fecha_previa = semana
    if fecha_previa is None:
        return resultado

    var_por_ticker = {}
    for ticker in config.TICKERS_FLUJOS:
        df = datos.get(ticker)
        if df is None:
            continue
        cierre = serie_cierre(df)
        _, var = _variacion_semanal(cierre, fechas_semana, fecha_previa)
        if var is not None:
            var_por_ticker[ticker] = var

    spreads = []
    for t_a, t_b, etiqueta in config.SPREADS_FLUJOS:
        if t_a not in var_por_ticker or t_b not in var_por_ticker:
            continue
        valor = var_por_ticker[t_a] - var_por_ticker[t_b]
        spreads.append({"a": t_a, "b": t_b, "etiqueta": etiqueta, "valor": float(valor)})

    if len(spreads) < 3:
        return resultado

    max_abs = max(abs(s["valor"]) for s in spreads) or 1e-9
    for s in spreads:
        s["barra_pct"] = round(abs(s["valor"]) / max_abs * 100, 1)

    volumen_rel = None
    df_spy = datos.get(config.TICKER_VOLUMEN_REFERENCIA)
    if df_spy is not None and "Volume" in df_spy.columns:
        vol = df_spy["Volume"].dropna()
        vol_semana = vol.reindex(fechas_semana).dropna()
        previas_desde = lunes - pd.Timedelta(weeks=config.SEMANAS_PROMEDIO_VOLUMEN)
        vol_previas = vol[(vol.index >= previas_desde) & (vol.index < lunes)]
        if not vol_semana.empty and not vol_previas.empty and vol_previas.mean() > 0:
            volumen_rel = vol_semana.mean() / vol_previas.mean() - 1

    resultado.update({
        "disponible": True,
        "spreads": spreads,
        "volumen_relativo": float(volumen_rel) if volumen_rel is not None else None,
    })
    return resultado


def calcular_todo(datos, fred_10y=None, referencia=None):
    """Orquesta S1-S4 sobre el dict de datos ya descargado."""
    s1 = calcular_s1(datos, referencia)
    if not s1["disponible"]:
        return {"s1": s1, "s2": {"disponible": False}, "s3": {"disponible": False}, "s4": {"disponible": False}}

    semana = (s1["semana"]["lunes"], s1["semana"]["viernes"], None, s1["semana"]["fecha_previa"])
    # recomponer fechas_semana reales a partir de los índices ya usados en S1
    fechas_semana = pd.DatetimeIndex(sorted({d["fecha"] for d in s1["spx"]["secuencia"]}))
    semana = (s1["semana"]["lunes"], s1["semana"]["viernes"], fechas_semana, s1["semana"]["fecha_previa"])

    s2 = calcular_s2(datos, semana)
    s3 = calcular_s3(datos, semana, fred_10y)
    s4 = calcular_s4(datos, semana)

    return {"s1": s1, "s2": s2, "s3": s3, "s4": s4, "semana": s1["semana"]}
