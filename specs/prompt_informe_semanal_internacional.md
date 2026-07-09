# PROMPT PARA CLAUDE CODE — Informe Semanal Internacional Automatizado

## Contexto

Soy asesor financiero. Quiero replicar un informe semanal de mercado estadounidense/global que se genera automáticamente cada sábado y se publica en GitHub Pages, para tenerlo listo el lunes a la mañana sin hacer research manual el fin de semana.

Este proyecto vive en un **repo dedicado**: `alphainvestment/Internacional` (público). Con GitHub Pages activado en este repo, el sitio se publica en `https://alphainvestment.github.io/Internacional/`. Existe otro repo (`Research`) de otro pipeline que no tiene nada que ver con este proyecto.

## Regla de oro

- Todo el trabajo ocurre **solo dentro de este repo** (`Internacional`).
- Todo el sistema debe ser **100% gratuito**: sin APIs pagas, sin servidores propios. Solo yfinance, Stooq (fallback), FRED (key gratuita) y GitHub Actions/Pages.
- El sistema debe correr **solo, sin intervención humana ni de IA**, todos los sábados.
- Primer paso del setup: verificar que GitHub Pages esté activado en el repo (Settings → Pages → Deploy from branch `main`, carpeta `/ (root)`); si no, indicar al usuario cómo activarlo.

## Arquitectura general

```
Internacional/                 ← raíz del repo
├── index.html                 ← archivo histórico: lista de informes por semana
├── informes/
│   └── 2026-07-03.html        ← un informe por semana (fecha = viernes de la semana)
├── scripts/
│   ├── main.py                ← orquestador
│   ├── data_sources.py        ← descarga con retry + fallback yfinance→Stooq
│   ├── calculos.py            ← métricas por sección
│   ├── narrativa.py           ← generación de textos por reglas (plantillas condicionales)
│   ├── render.py              ← generación del HTML final
│   ├── config.py              ← tickers, umbrales, constantes
│   ├── constituyentes_sp500.csv  ← lista de componentes (fase 2)
│   └── requirements.txt
├── specs/
│   └── prompt_informe_semanal_internacional.md  ← este archivo
└── .github/workflows/
    └── informe_internacional.yml   ← cron sábado
```

Las URLs públicas quedan: índice en `https://alphainvestment.github.io/Internacional/` e informes en `https://alphainvestment.github.io/Internacional/informes/YYYY-MM-DD.html`.

Lenguaje: **Python 3.11+**, sin frameworks. Librerías permitidas: `yfinance`, `pandas`, `numpy`, `requests`, `jinja2` (para el template HTML). Nada más.

## Cron / Workflow de GitHub Actions

- Cron: sábado 10:00 AM hora Córdoba, Argentina (UTC-3) → `0 13 * * 6` en UTC.
- Permitir también disparo manual (`workflow_dispatch`) para testear.
- Pasos: checkout → setup Python → pip install → correr `main.py` → commit + push del HTML nuevo y del index actualizado.
- Si el script falla, el job debe fallar (exit code ≠ 0) para que GitHub mande la notificación por mail. **Nunca publicar un HTML incompleto o con datos vacíos**: validar antes de escribir.
- La FRED API key va en GitHub Secrets como `FRED_API_KEY`. El script la lee de variable de entorno.

## Semana a reportar

El informe cubre **lunes a viernes de la semana que acaba de terminar**. Si el sábado corre el job, reporta la semana que cerró el viernes anterior. Manejar feriados de mercado USA: si el viernes fue feriado, el cierre semanal es el último día hábil. Usar el calendario implícito en los datos (última fecha con precio), no hardcodear feriados.

## FASES DE DESARROLLO

Implementar en este orden. Cada fase debe quedar funcionando y publicable antes de pasar a la siguiente.

---

### FASE 1 (v1) — Núcleo del informe

Secciones a implementar:

**S1. Panorama de mercado**
- Tickers: `^GSPC`, `^IXIC`, `^DJI`, `^RUT`, `^VIX`.
- Métricas: variación semanal %, cierre, secuencia día a día (+/− por sesión), mejor y peor sesión de la semana.
- VIX: nivel de cierre y variación semanal %.

**S2. Rotación sectorial**
- Los 11 ETFs sectoriales SPDR: XLF, XLC, XLY, XLV, XLI, XLB, XLP, XLK, XLU, XLE, XLRE.
- Variación semanal % de cada uno, ordenados de mayor a menor, con barra horizontal visual (verde positivo / rojo negativo).
- Métricas derivadas: cuántos de 11 en positivo; spread cíclicos vs defensivos (cíclicos: XLF, XLY, XLI, XLB, XLK, XLC; defensivos: XLP, XLU, XLV, XLRE; promedio simple de cada grupo).

**S3. Divisas y macro global**
- FX: EURUSD=X, GBPUSD=X, JPY=X, CHF=X, AUDUSD=X, CAD=X, CNY=X, MXN=X, BRL=X. Cierre + variación semanal. Convención: para pares USD/XXX una suba del par = dólar más fuerte; expresarlo desde la perspectiva de la divisa (ej: "Yen −0.3% vs USD").
- Índice sintético del dólar: promedio ponderado simple de la variación contra majors (EUR 40%, JPY 20%, GBP 15%, CHF 10%, AUD 7.5%, CAD 7.5%).
- Macro: Oro (GC=F), WTI (CL=F), Bitcoin (BTC-USD), VIX (ya bajado), Tasa 10Y de FRED (serie `DGS10`), variación en puntos básicos.

**S4. Flujos: institucionales vs minoristas (proxies)**
- 4 spreads semanales: RSP−SPY (equiponderado vs cap-ponderado), IWM−SPY (small caps vs large), SPHB−SPLV (alta beta vs baja vol), HYG−TLT (crédito HY vs Treasuries largos).
- Volumen del SPY de la semana vs promedio de las 4 semanas previas (% de diferencia).
- Barras horizontales por spread + una línea de lectura por reglas (ver narrativa).

**S5. Resumen ejecutivo + Claves de la semana + tarjetas de cabecera**
- Todo generado por reglas a partir de las métricas ya calculadas (ver sección Narrativa).
- Tarjetas de cabecera (v1): S&P 500 %, VIX (nivel y var), USD (índice sintético), Mejor sector, Peor sector, Spread cíclicos−defensivos.

**S10. Notificación por mail vía GitHub Release**
- Al final del workflow, después del push exitoso, crear un **Release** en el repo con:
  - Tag: `internacional-YYYY-MM-DD` (fecha del viernes de la semana reportada)
  - Título: el título generado del informe (ej: "El S&P 500 avanzó (+1.8%) en una semana de apetito por riesgo amplio")
  - Cuerpo: rango de fechas de la semana, las "Claves de la semana" en bullets, y el link directo al HTML publicado (`https://alphainvestment.github.io/Internacional/informes/YYYY-MM-DD.html`)
- Usar `gh release create` o la action `softprops/action-gh-release` con el `GITHUB_TOKEN` automático del workflow (no requiere ningún secret adicional ni credencial personal).
- El usuario activa Watch → Custom → Releases en el repo una sola vez; GitHub le envía el mail automáticamente cada sábado.
- Si la creación del Release falla, NO abortar: el informe ya está publicado; loguear el error y terminar con éxito (el Release es notificación, no núcleo).

> **Upgrade opcional futuro (no implementar ahora):** migrar la notificación a un mail con formato propio usando un servicio transaccional gratuito (Brevo, 300/día free, o Resend, 100/día free) con API key en GitHub Secrets. Documentado aquí solo como referencia.

---

### FASE 2 (v2) — Amplitud y componentes

**S6. Amplitud del mercado**
- Fuente de constituyentes: mantener `constituyentes_sp500.csv` en el repo (ticker, nombre, sector GICS). Incluir un script auxiliar `actualizar_constituyentes.py` que lo regenere scrapeando la tabla de Wikipedia (List of S&P 500 companies), para correr manualmente cada tanto. El pipeline semanal lee el CSV, no scrapea.
- Descarga de los ~500 en chunks de 100 tickers con `yf.download()`, retry con backoff exponencial (3 intentos, 5/15/45 seg), y tolerancia: si un ticker falla, se excluye y se reporta el N efectivo.
- Métricas: suben / bajan / planos (|var| < 0.25%); amplitud %; retorno promedio y mediana por compañía vs retorno del índice; % de compañías sobre su EMA 50 y EMA 200 (necesita ≥200 ruedas de historia); amplitud media diaria (% de tickers al alza por sesión, promedio de la semana).

**S7. Distribución de retornos semanales**
- Histograma con 6 buckets: < −5%, −5 a −2%, −2 a 0%, 0 a +2%, +2 a +5%, > +5%. Barras verticales rojas/verdes con el conteo arriba.

**S8. Ganadores y perdedores**
- Top 10 subas y top 10 bajas de la semana entre los componentes, con ticker, nombre y %.
- Línea de lectura por reglas: sectores predominantes entre ganadores y entre perdedores (usando el sector GICS del CSV).

---

### FASE 3 (v3) — Earnings

**S9. Temporada de resultados**
- Fuente: Finnhub free tier (key gratuita en GitHub Secrets como `FINNHUB_API_KEY`). Endpoint de earnings calendar de la semana.
- Filtrar: reportes de compañías del S&P 500 (cruzar contra el CSV de constituyentes).
- Por reporte: EPS actual vs estimado, sorpresa %, y reacción del precio (variación del día siguiente si reportó after-market, o del mismo día si reportó pre-market — si Finnhub no da el timing, usar día siguiente y etiquetar "día sig.").
- Agregados: N reportes, % de beats, sorpresa media.
- Respetar rate limit free (60 calls/min): con 4–20 reportes semanales sobra, pero poner un sleep de 1.1 seg entre calls por prolijidad.

---

## Narrativa por reglas (narrativa.py)

Sin IA. Plantillas condicionales en español neutro-profesional (no rioplatense: es un informe institucional). Ejemplos de reglas:

- **Régimen de la semana** (para título y resumen):
  - SPX > +1.5% y amplitud > 55% (o en v1: ≥7 sectores en positivo) → "apetito por riesgo amplio"
  - SPX > +1.5% y amplitud < 45% → "suba concentrada"
  - |SPX| ≤ 0.5% → "semana de consolidación"
  - SPX < −1.5% y amplitud < 45% → "aversión al riesgo generalizada"
  - Resto → "semana mixta"
- **Título**: "El S&P 500 {avanzó/retrocedió} ({±X.X%}) en una semana de {régimen}".
- **Balance agregado** (escala −100/+100): score compuesto = promedio normalizado de: signo y magnitud del SPX (peso 30), amplitud sectorial (20), spread cíclicos−defensivos (15), variación del VIX invertida (15), spread HY−TLT (10), dólar invertido (10). Redondear a entero. Documentar la fórmula en un comentario.
- **Lectura de flujos**: si los 4 spreads tienen |valor| < 1% → "sin sesgo dominante; la señal más honesta es de equilibrio". Si RSP−SPY y SPHB−SPLV positivos → "participación amplia con apetito por beta". Etc. — definir 5–6 casos y un default neutro.
- Cada sección lleva 1–3 párrafos generados así. Preferir frases cortas, tono de research bancario, sin adjetivos vacíos.

## Template HTML (render.py + Jinja2)

- Un solo archivo HTML autocontenido por semana: CSS inline en `<style>`, sin JS, sin librerías externas, sin imágenes (los gráficos de barras se hacen con divs y CSS; el histograma también).
- Estética institucional sobria: fondo blanco, tipografía system-ui/Segoe/Helvetica, paleta navy (#1a2b4a aprox.) para títulos y acentos, verde (#0d9463) para positivos, rojo (#d13438) para negativos, grises para bordes y metadatos.
- Estructura: cabecera con "INFORME SEMANAL DE MERCADO — INTERNACIONAL", rango de fechas, título generado, bajada, fila de tarjetas de métricas clave; luego secciones numeradas (01, 02, ...) con barra corta navy sobre el número; tablas limpias con zebra striping suave; footer con el rango de la semana y paginación implícita (es una sola página web, no PDF).
- Responsive básico: que se lea bien en el celular (tablas con overflow-x, tarjetas que hacen wrap).
- `index.html` del directorio: lista reverse-cronológica de informes con título generado y link, mismo lenguaje visual.
- **Disclaimer al pie**: "Informe generado automáticamente con datos públicos. No constituye recomendación de inversión."

## data_sources.py — Robustez

- Función única `descargar(tickers, periodo)` con: retry con backoff (3 intentos), fallback a Stooq para índices/FX/commodities si yfinance devuelve vacío (mapear símbolos: ^GSPC→^SPX en Stooq, etc.), y validación de que hay ≥4 sesiones en la semana.
- Si una sección entera no puede calcularse, el informe se genera igual con esa sección marcada "Datos no disponibles esta semana" — **salvo** que fallen S1 o S3 (núcleo): en ese caso abortar con exit code 1 y no publicar.
- Cachear en memoria: una sola descarga por ticker por corrida.

## Criterios de aceptación

**Fase 1:**
1. `python scripts/main.py` local genera `informes/YYYY-MM-DD.html` completo con S1–S5 y datos reales de la última semana cerrada.
2. El HTML se ve correcto en desktop y mobile, sin recursos externos.
3. El workflow corre con `workflow_dispatch` en GitHub y publica correctamente.
4. Forzar un fallo de yfinance (ej: ticker inválido) activa el fallback o el aborto según corresponda, y el job falla visiblemente si es núcleo.
5. GitHub Pages sirve el índice y el informe en las URLs públicas esperadas.
6. El index.html lista el informe nuevo arriba de todo.
7. Al terminar el workflow queda creado el Release con título, claves y link correctos; un fallo en el Release no impide la publicación del informe.

**Fase 2:**
8. La descarga de ~500 tickers completa en <10 min en Actions, con N efectivo reportado.
9. Amplitud, EMA 50/200, histograma y top 10 coinciden con verificación manual de 5 tickers al azar.

**Fase 3:**
10. Earnings de la semana coinciden con lo publicado por las compañías (verificar 2 casos).
11. Si Finnhub no responde, la sección se marca no disponible y el resto del informe se publica igual.

## Qué NO hacer

- No usar APIs pagas ni con free trial que expire.
- No agregar JS, frameworks front, ni build steps para el HTML.
- No trabajar fuera de este repo ni tocar otros repos de la cuenta.
- No hardcodear la fecha: todo derivado del calendario de datos.
- No publicar si el núcleo (S1/S3) no tiene datos válidos.

## Empezar por

1. Crear la estructura de carpetas y `config.py` con todos los tickers.
2. `data_sources.py` con descarga + retry + fallback.
3. `calculos.py` para S1–S4.
4. `narrativa.py` con las reglas.
5. `render.py` + template.
6. `main.py` orquestando y validando.
7. Workflow YAML.
8. Correr local, revisar el HTML juntos, ajustar, y recién ahí activar el cron.
