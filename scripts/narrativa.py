"""Generación de textos por reglas (sin IA). Español neutro-profesional,
tono de research bancario. Toma las estructuras de calculos.py y devuelve
strings/listas listos para el template.
"""

import config


def _fmt_pct(x, decimales=1, signo=True):
    if x is None:
        return "s/d"
    valor = round(x * 100, decimales)
    if valor == 0:
        valor = 0.0  # evita "-0.0%" cuando el redondeo cruza el cero
    prefijo = "+" if signo and valor >= 0 else ""
    return f"{prefijo}{valor:.{decimales}f}%"


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


# --------------------------------------------------------------------------
# Régimen de la semana y título
# --------------------------------------------------------------------------

def regimen_semana(var_spx, sectores_positivos, total_sectores):
    """Clasifica el régimen de la semana. Regla v1 (spec): se usa
    "≥7 de 11 sectores en positivo" como proxy de "amplitud > 55%" porque
    la amplitud de mercado real (S6) recién se calcula en fase 2.
    """
    if total_sectores:
        amplia = sectores_positivos >= 7
        concentrada = (sectores_positivos / total_sectores) < 0.45
    else:
        amplia = False
        concentrada = False

    if var_spx > 0.015 and amplia:
        return "apetito por riesgo amplio"
    if var_spx > 0.015 and concentrada:
        return "suba concentrada"
    if abs(var_spx) <= 0.005:
        return "semana de consolidación"
    if var_spx < -0.015 and concentrada:
        return "aversión al riesgo generalizada"
    return "semana mixta"


def titulo_informe(var_spx, regimen):
    verbo = "avanzó" if var_spx >= 0 else "retrocedió"
    return f"El S&P 500 {verbo} ({_fmt_pct(var_spx)}) en una semana de {regimen}"


def bajada_informe(s2, s3):
    """Segunda línea de cabecera: una frase con sectores + dólar/VIX."""
    partes = []
    if s2.get("disponible"):
        partes.append(
            f"{s2['positivos']} de {s2['total']} sectores en positivo, "
            f"liderados por {s2['mejor']['nombre']} ({_fmt_pct(s2['mejor']['var'])})"
        )
    if s3.get("disponible") and s3.get("indice_usd") is not None:
        direccion = "se fortaleció" if s3["indice_usd"] >= 0 else "se debilitó"
        partes.append(f"el dólar {direccion} {_fmt_pct(abs(s3['indice_usd']), signo=False)} frente a las majors")
    if not partes:
        return "Resumen no disponible por falta de datos."
    return "; ".join(partes) + "."


# --------------------------------------------------------------------------
# Balance agregado (-100 / +100)
# --------------------------------------------------------------------------

def balance_agregado(var_spx, sectores_positivos, total_sectores, spread_cd, var_vix, spread_hy_tlt, indice_usd):
    """Score compuesto -100..+100.

    Ponderación (spec): SPX 30, amplitud sectorial 20, spread cíclicos-
    defensivos 15, VIX invertido 15, spread HY-TLT 10, dólar invertido 10.

    Cada componente se normaliza a [-1, 1] dividiendo por un techo empírico
    de "movimiento semanal grande" antes de aplicar el peso, para que
    ninguna sección domine el score por tener una escala naturalmente mayor
    (el VIX se mueve semana a semana mucho más que el USD, por ejemplo).
    """
    componente_spx = _clip(var_spx / 0.03, -1, 1) * 30

    amplitud = (sectores_positivos / total_sectores) if total_sectores else 0.5
    componente_amplitud = _clip((amplitud - 0.5) * 2, -1, 1) * 20

    componente_cd = _clip((spread_cd or 0.0) / 0.02, -1, 1) * 15 if spread_cd is not None else 0.0

    componente_vix = -_clip((var_vix or 0.0) / 0.15, -1, 1) * 15 if var_vix is not None else 0.0

    componente_hy = _clip((spread_hy_tlt or 0.0) / 0.02, -1, 1) * 10 if spread_hy_tlt is not None else 0.0

    componente_usd = -_clip((indice_usd or 0.0) / 0.01, -1, 1) * 10 if indice_usd is not None else 0.0

    score = componente_spx + componente_amplitud + componente_cd + componente_vix + componente_hy + componente_usd
    return int(round(_clip(score, -100, 100)))


# --------------------------------------------------------------------------
# Lectura de flujos (S4)
# --------------------------------------------------------------------------

def lectura_flujos(spreads):
    """spreads: lista de dicts {a, b, etiqueta, valor} de calcular_s4."""
    valores = {(s["a"], s["b"]): s["valor"] for s in spreads}
    rsp_spy = valores.get(("RSP", "SPY"))
    iwm_spy = valores.get(("IWM", "SPY"))
    sphb_splv = valores.get(("SPHB", "SPLV"))
    hyg_tlt = valores.get(("HYG", "TLT"))
    presentes = [v for v in (rsp_spy, iwm_spy, sphb_splv, hyg_tlt) if v is not None]

    if presentes and all(abs(v) < 0.01 for v in presentes):
        return (
            "Los cuatro proxies de flujos no muestran sesgo dominante; "
            "la señal más honesta es de equilibrio entre institucionales y minoristas."
        )

    if rsp_spy is not None and sphb_splv is not None and rsp_spy > 0 and sphb_splv > 0:
        return (
            "La participación fue amplia y con apetito por beta: el equiponderado "
            "superó al índice cap-ponderado y los nombres de alta beta superaron a "
            "los defensivos de baja volatilidad."
        )

    if rsp_spy is not None and sphb_splv is not None and rsp_spy < 0 and sphb_splv < 0:
        return (
            "La señal de flujos es defensiva: el cap-ponderado superó al "
            "equiponderado y los nombres de baja volatilidad superaron a los de "
            "alta beta."
        )

    if hyg_tlt is not None and hyg_tlt > 0.01:
        return (
            "El crédito high-yield superó con holgura a los Treasuries largos, "
            "un indicio de apetito por riesgo en el mercado de renta fija."
        )

    if hyg_tlt is not None and hyg_tlt < -0.01:
        return (
            "Los Treasuries largos superaron al crédito high-yield, coherente con "
            "una postura más defensiva en renta fija."
        )

    if iwm_spy is not None and iwm_spy > 0.01:
        return "Las small caps superaron a las large caps en la semana, un signo de mayor apetito por riesgo relativo."

    if iwm_spy is not None and iwm_spy < -0.01:
        return "Las large caps superaron a las small caps, reflejando preferencia por calidad y liquidez."

    return "Los proxies de flujos muestran señales mixtas, sin un sesgo claro entre apetito institucional y minorista."


# --------------------------------------------------------------------------
# Lecturas mínimas por sección (S1-S3): una frase de contexto para que cada
# sección no quede como una tabla o barra "muda".
# --------------------------------------------------------------------------

def lectura_panorama(s1):
    indices = s1.get("indices", {})
    comparables = {t: i for t, i in indices.items() if t != config.TICKER_VIX}
    if not comparables:
        return None

    mejor = max(comparables.values(), key=lambda i: i["var"])
    peor = min(comparables.values(), key=lambda i: i["var"])
    frase = f"{mejor['nombre']} lideró entre los principales índices ({_fmt_pct(mejor['var'])}); {peor['nombre']} quedó más rezagado ({_fmt_pct(peor['var'])})."

    vix = s1.get("vix")
    if vix is not None:
        if vix["var"] <= -0.08:
            frase += " La fuerte caída del VIX confirma una compresión marcada de la volatilidad implícita."
        elif vix["var"] >= 0.08:
            frase += " El salto del VIX refleja una demanda de cobertura más alta de lo habitual."
        else:
            frase += " El VIX se mantuvo relativamente estable, sin señales adicionales de estrés."
    return frase


def lectura_sectores(s2):
    if not s2.get("disponible"):
        return None
    spread = s2.get("spread_ciclicos_defensivos")
    if spread is None:
        return None
    if spread > 0.01:
        return "La rotación favoreció a los sectores cíclicos por sobre los defensivos, un patrón habitual en fases de apetito por riesgo."
    if spread < -0.01:
        return "Los sectores defensivos superaron a los cíclicos, un sesgo más cauteloso dentro de la rotación semanal."
    return "Cíclicos y defensivos se movieron de forma pareja, sin una rotación clara en ninguna dirección."


def lectura_macro(s3):
    if not s3.get("disponible"):
        return None
    piezas = []

    if s3.get("indice_usd") is not None:
        usd = s3["indice_usd"]
        if usd > 0.005:
            piezas.append("el dólar se fortaleció frente a la mayoría de las majors")
        elif usd < -0.005:
            piezas.append("el dólar se debilitó frente a la mayoría de las majors")
        else:
            piezas.append("el dólar operó sin una dirección clara frente a las majors")

    tasa = s3.get("tasa_10y")
    if tasa is not None:
        if tasa["var_pb"] >= 5:
            piezas.append(f"la tasa a 10 años subió {tasa['var_pb']:.0f} pb, presionando a los activos de mayor duración")
        elif tasa["var_pb"] <= -5:
            piezas.append(f"la tasa a 10 años bajó {abs(tasa['var_pb']):.0f} pb, un alivio para los activos de mayor duración")

    macro = s3.get("macro", {})
    oro, btc = macro.get("GC=F"), macro.get("BTC-USD")
    if oro is not None and btc is not None:
        if oro["var"] > 0 and btc["var"] > 0:
            piezas.append("tanto el oro como Bitcoin avanzaron, un indicio de apetito por activos alternativos")
        elif oro["var"] < 0 and btc["var"] < 0:
            piezas.append("tanto el oro como Bitcoin retrocedieron en la semana")

    if not piezas:
        return None
    frase = "; ".join(piezas) + "."
    return frase[0].upper() + frase[1:]


# --------------------------------------------------------------------------
# Resumen ejecutivo y claves de la semana
# --------------------------------------------------------------------------

def resumen_ejecutivo(s1, s2, s3, s4, regimen):
    parrafos = []

    spx = s1["spx"]
    vix = s1.get("vix")
    p1 = f"El S&P 500 {'avanzó' if spx['var'] >= 0 else 'retrocedió'} {_fmt_pct(spx['var'])} en la semana, cerrando en {spx['cierre']:,.0f} puntos, en un contexto de {regimen}."
    if vix is not None:
        direccion_vix = "subió" if vix["var"] >= 0 else "bajó"
        p1 += f" El VIX {direccion_vix} {_fmt_pct(abs(vix['var']), signo=False)} y cerró en {vix['cierre']:.1f}."
    parrafos.append(p1)

    if s2.get("disponible"):
        p2 = (
            f"La rotación sectorial mostró {s2['positivos']} de {s2['total']} sectores en terreno positivo. "
            f"{s2['mejor']['nombre']} lideró con {_fmt_pct(s2['mejor']['var'])}, mientras que "
            f"{s2['peor']['nombre']} fue el más rezagado con {_fmt_pct(s2['peor']['var'])}."
        )
        if s2.get("spread_ciclicos_defensivos") is not None:
            spread = s2["spread_ciclicos_defensivos"]
            sesgo = "a favor de los cíclicos" if spread > 0 else "a favor de los defensivos"
            p2 += f" El spread cíclicos-defensivos quedó {sesgo} ({_fmt_pct(spread)})."
        parrafos.append(p2)

    if s3.get("disponible"):
        piezas = []
        if s3.get("indice_usd") is not None:
            direccion = "se fortaleció" if s3["indice_usd"] >= 0 else "se debilitó"
            piezas.append(f"el dólar {direccion} {_fmt_pct(abs(s3['indice_usd']), signo=False)} frente a una canasta de majors")
        if s3.get("tasa_10y"):
            t = s3["tasa_10y"]
            direccion_t = "subió" if t["var_pb"] >= 0 else "bajó"
            piezas.append(f"la tasa a 10 años {direccion_t} {abs(t['var_pb']):.0f} pb hasta {t['nivel']:.2f}%")
        oro = s3.get("macro", {}).get("GC=F")
        wti = s3.get("macro", {}).get("CL=F")
        btc = s3.get("macro", {}).get("BTC-USD")
        if oro is not None:
            piezas.append(f"el oro {_fmt_pct(oro['var'])}")
        if wti is not None:
            piezas.append(f"el WTI {_fmt_pct(wti['var'])}")
        if btc is not None:
            piezas.append(f"Bitcoin {_fmt_pct(btc['var'])}")
        if piezas:
            parrafos.append("En el frente macro, " + "; ".join(piezas) + ".")

    if s4.get("disponible"):
        parrafos.append(lectura_flujos(s4["spreads"]))

    return parrafos


def claves_semana(s1, s2, s3, s4):
    claves = []
    spx = s1["spx"]
    claves.append(f"S&P 500: {_fmt_pct(spx['var'])} en la semana, cierre en {spx['cierre']:,.0f}.")

    vix = s1.get("vix")
    if vix is not None:
        claves.append(f"VIX en {vix['cierre']:.1f} ({_fmt_pct(vix['var'])} en la semana).")

    if s2.get("disponible"):
        claves.append(
            f"Sector líder: {s2['mejor']['nombre']} ({_fmt_pct(s2['mejor']['var'])}); "
            f"más rezagado: {s2['peor']['nombre']} ({_fmt_pct(s2['peor']['var'])})."
        )

    if s3.get("disponible") and s3.get("indice_usd") is not None:
        direccion = "se fortaleció" if s3["indice_usd"] >= 0 else "se debilitó"
        claves.append(f"Dólar (índice sintético): {direccion} {_fmt_pct(abs(s3['indice_usd']), signo=False)}.")

    if s3.get("disponible") and s3.get("tasa_10y"):
        t = s3["tasa_10y"]
        claves.append(f"Tasa 10Y: {t['nivel']:.2f}% ({t['var_pb']:+.0f} pb en la semana).")

    if s4.get("disponible") and s4.get("volumen_relativo") is not None:
        claves.append(f"Volumen SPY vs. promedio 4 semanas: {_fmt_pct(s4['volumen_relativo'])}.")

    return claves


def generar_informe(resultado):
    """Punto de entrada: recibe el dict de calcular_todo() y devuelve todos
    los textos que necesita el template."""
    s1, s2, s3, s4 = resultado["s1"], resultado["s2"], resultado["s3"], resultado["s4"]
    spx = s1["spx"]
    vix = s1.get("vix")

    sectores_positivos = s2.get("positivos", 0)
    total_sectores = s2.get("total", 0)
    regimen = regimen_semana(spx["var"], sectores_positivos, total_sectores)

    balance = balance_agregado(
        var_spx=spx["var"],
        sectores_positivos=sectores_positivos,
        total_sectores=total_sectores,
        spread_cd=s2.get("spread_ciclicos_defensivos"),
        var_vix=vix["var"] if vix else None,
        spread_hy_tlt=next((s["valor"] for s in s4.get("spreads", []) if s["a"] == "HYG"), None),
        indice_usd=s3.get("indice_usd"),
    )

    return {
        "regimen": regimen,
        "titulo": titulo_informe(spx["var"], regimen),
        "bajada": bajada_informe(s2, s3),
        "balance": balance,
        "resumen": resumen_ejecutivo(s1, s2, s3, s4, regimen),
        "claves": claves_semana(s1, s2, s3, s4),
        "lectura_panorama": lectura_panorama(s1),
        "lectura_sectores": lectura_sectores(s2),
        "lectura_macro": lectura_macro(s3),
        "lectura_flujos": lectura_flujos(s4["spreads"]) if s4.get("disponible") else None,
    }
