"""
Panel Limousin España — índice de parición y espacio interpartos, por
Comunidad Autónoma o por provincia, con mapas interactivos (Plotly),
filtro y "Limusin GPT" (panel de IA conversacional) a la derecha.

Todo usa el AÑO NATURAL 2025 (1 enero - 31 diciembre) para que sea
comparable — ver docs/conclusiones_investigacion_limusin.md y
docs/kpis_ganadero_agentico.md.

Lanzar con: streamlit run app/limusin_dashboard.py
"""
import json
import os
import re
import sys
import threading
import urllib.request

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    AI_PROVIDER,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO_PATH = os.path.join(REPO_ROOT, "Logo_ixorigue-BpQt6KE7.png")
PROMPTS_DIR = os.path.join(REPO_ROOT, "docs", "prompts")

# Qué prompt de docs/prompts/recomendaciones_prompt_{tier}_model.md usar
# según el modelo activo — ver docs/prompts/README.md para el porqué. Un
# modelo NO listado aquí cae en "small" por defecto (más prudente asumir
# limitado que asumir capaz sin haberlo probado). Para cambiar de modelo
# sin tocar código, basta con añadir su entrada aquí.
MODEL_TIERS = {
    "llama-3.1-8b-instant": "small",
    "llama-3.3-70b-versatile": "large",
    "claude-sonnet-4-6": "large",
    "gemini-2.5-flash": "large",
    "gemini-2.5-pro": "large",
    "gemini-3.6-flash": "large",
    "gemini-3.6-pro": "large",
}
CCAA_GEOJSON_URL = "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/spain-communities.geojson"
PROV_GEOJSON_URL = "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/spain-provinces.geojson"

MUTED = "#898781"
NO_DATA_COLOR = "#e4e2dc"
BRAND_GREEN = "#8dc63f"
INK = "#0b0b0b"

# Altura compartida por mapa, ranking y chat de Limusin GPT — pensada para
# que el dashboard completo quepa en una pantalla típica sin necesidad de
# hacer scroll hacia abajo para ver el conjunto.
VIS_HEIGHT = 460

CCAA_NAME_MAP = {
    "Castilla-Leon": "Castilla y León",
    "Cataluña": "Cataluña",
    "Valencia": "C. Valenciana",
    "Andalucia": "Andalucía",
    "Aragon": "Aragón",
    "Pais Vasco": "País Vasco",
    "Castilla-La Mancha": "Castilla-La Mancha",
    "Extremadura": "Extremadura", "Galicia": "Galicia", "Madrid": "Madrid",
    "Navarra": "Navarra", "La Rioja": "La Rioja", "Cantabria": "Cantabria",
    "Asturias": "Asturias",
    # Sin ganaderías Limousin (sin dato) pero SÍ deben aparecer en gris en el
    # mapa en vez de como un hueco invisible — hay que darles un canon_name
    # válido aunque no estén en PARICION_CCAA_2025/INTERPARTO_CCAA_2025.
    "Murcia": "Murcia", "Ceuta": "Ceuta", "Melilla": "Melilla",
    "Baleares": "Illes Balears",
}

# ---------------------------------------------------------------- datos: CCAA
# Índice de parición, año natural 2025 (ver scripts/mapas/gen_mapa_limusin_paricion_2025.py)
PARICION_CCAA_2025 = {
    "País Vasco":          {"n": 3542,  "valor": 74.5},
    "Andalucía":           {"n": 1597,  "valor": 71.6},
    "Extremadura":         {"n": 6001,  "valor": 70.0},
    "Asturias":            {"n": 176,   "valor": 67.0},
    "C. Valenciana":       {"n": 11,    "valor": 63.6},
    "Castilla y León":     {"n": 7376,  "valor": 63.4},
    "Aragón":              {"n": 441,   "valor": 62.8},
    "Galicia":             {"n": 1148,  "valor": 60.0},
    "Navarra":             {"n": 54,    "valor": 59.3},
    "Castilla-La Mancha":  {"n": 1671,  "valor": 59.2},
    "La Rioja":            {"n": 49,    "valor": 55.1},
    "Cataluña":            {"n": 307,   "valor": 53.4},
    "Cantabria":           {"n": 10922, "valor": 50.6},
    "Madrid":              {"n": 881,   "valor": 49.6},
}
INTERPARTO_CCAA_2025 = {
    "Madrid":              {"n": 273,  "valor": 384, "pct365": 46.5},
    "Cataluña":            {"n": 107,  "valor": 385, "pct365": 43.0},
    "Castilla-La Mancha":  {"n": 607,  "valor": 390, "pct365": 44.0},
    "Aragón":              {"n": 210,  "valor": 391, "pct365": 37.1},
    "Asturias":            {"n": 88,   "valor": 391, "pct365": 29.5},
    "Galicia":             {"n": 413,  "valor": 392, "pct365": 40.9},
    "Extremadura":         {"n": 2967, "valor": 395, "pct365": 37.7},
    "Cantabria":           {"n": 3364, "valor": 396, "pct365": 38.2},
    "País Vasco":          {"n": 1974, "valor": 397, "pct365": 36.7},
    "Castilla y León":     {"n": 3236, "valor": 399, "pct365": 39.0},
    "Andalucía":           {"n": 782,  "valor": 400, "pct365": 36.3},
}

# ---------------------------------------------------------------- datos: PROVINCIA
# Mismas queries que CCAA pero SIN agregar Ranches.ExtraData->state a CCAA
# (código INE de provincia crudo). Ejecutado 2026-07-29 contra el tenant
# Limousin. Claves = código INE de provincia (como string, para casar
# directo con la propiedad "cod_prov" del geojson de provincias, sin líos
# de acentos/encoding en el nombre).
PROVINCIA_NAME = {
    "01": "Álava", "02": "Albacete", "05": "Ávila", "06": "Badajoz", "08": "Barcelona",
    "09": "Burgos", "10": "Cáceres", "11": "Cádiz", "12": "Castellón", "13": "Ciudad Real",
    "14": "Córdoba", "15": "A Coruña", "17": "Girona", "19": "Guadalajara", "20": "Gipuzkoa",
    "21": "Huelva", "22": "Huesca", "24": "León", "25": "Lleida", "26": "La Rioja",
    "27": "Lugo", "28": "Madrid", "29": "Málaga", "31": "Navarra", "32": "Ourense",
    "33": "Asturias", "34": "Palencia", "36": "Pontevedra", "37": "Salamanca", "39": "Cantabria",
    "40": "Segovia", "41": "Sevilla", "42": "Soria", "44": "Teruel", "45": "Toledo",
    "47": "Valladolid", "48": "Bizkaia", "49": "Zamora", "50": "Zaragoza",
}
N_RANCHOS_PROV = {
    "39": 479, "10": 106, "20": 89, "37": 74, "05": 73, "48": 66, "06": 49, "27": 40,
    "45": 35, "28": 33, "01": 29, "09": 28, "14": 26, "24": 20, "33": 15, "40": 14,
    "21": 13, "36": 12, "11": 11, "49": 11, "41": 11, "42": 11, "32": 10, "15": 9,
    "13": 8, "44": 7, "34": 6, "31": 5, "47": 5, "26": 4, "50": 3, "25": 2, "19": 2,
    "17": 2, "22": 2, "12": 1, "02": 1, "29": 1, "08": 1,
}
PARICION_PROV_2025 = {
    "29": {"n": 56,   "valor": 92.9}, "17": {"n": 146,  "valor": 89.7},
    "01": {"n": 668,  "valor": 85.3}, "47": {"n": 114,  "valor": 83.3},
    "44": {"n": 319,  "valor": 77.4}, "19": {"n": 97,   "valor": 74.2},
    "41": {"n": 441,  "valor": 73.9}, "48": {"n": 1003, "valor": 73.3},
    "06": {"n": 2151, "valor": 73.3}, "11": {"n": 323,  "valor": 72.4},
    "20": {"n": 1871, "valor": 71.3}, "14": {"n": 617,  "valor": 70.3},
    "42": {"n": 284,  "valor": 69.4}, "37": {"n": 2172, "valor": 69.0},
    "10": {"n": 3852, "valor": 68.1}, "05": {"n": 2108, "valor": 67.4},
    "33": {"n": 176,  "valor": 67.0}, "02": {"n": 27,   "valor": 66.7},
    "12": {"n": 11,   "valor": 63.6}, "32": {"n": 255,  "valor": 63.5},
    "40": {"n": 428,  "valor": 62.9}, "09": {"n": 1131, "valor": 62.1},
    "21": {"n": 159,  "valor": 61.0}, "27": {"n": 681,  "valor": 60.4},
    "45": {"n": 1285, "valor": 60.3}, "31": {"n": 54,   "valor": 59.3},
    "15": {"n": 82,   "valor": 58.5}, "34": {"n": 250,  "valor": 58.4},
    "26": {"n": 49,   "valor": 55.1}, "36": {"n": 127,  "valor": 52.0},
    "39": {"n": 10922,"valor": 50.6}, "28": {"n": 881,  "valor": 49.6},
    "13": {"n": 262,  "valor": 47.7}, "49": {"n": 426,  "valor": 46.5},
    "50": {"n": 75,   "valor": 36.0}, "24": {"n": 463,  "valor": 33.7},
    "08": {"n": 141,  "valor": 23.4}, "22": {"n": 47,   "valor": 6.4},
    "25": {"n": 20,   "valor": 0.0},
}
INTERPARTO_PROV_2025 = {
    "49": {"n": 139,  "valor": 371, "pct365": 64.7}, "19": {"n": 59,   "valor": 372, "pct365": 49.2},
    "47": {"n": 76,   "valor": 376, "pct365": 47.4}, "36": {"n": 39,   "valor": 379, "pct365": 51.3},
    "32": {"n": 114,  "valor": 383, "pct365": 48.2}, "17": {"n": 84,   "valor": 383, "pct365": 44.0},
    "28": {"n": 273,  "valor": 384, "pct365": 46.5}, "44": {"n": 194,  "valor": 387, "pct365": 39.2},
    "40": {"n": 189,  "valor": 391, "pct365": 47.6}, "45": {"n": 494,  "valor": 391, "pct365": 44.5},
    "33": {"n": 88,   "valor": 391, "pct365": 29.5}, "08": {"n": 23,   "valor": 392, "pct365": 39.1},
    "01": {"n": 426,  "valor": 393, "pct365": 41.8}, "14": {"n": 290,  "valor": 393, "pct365": 39.0},
    "15": {"n": 38,   "valor": 395, "pct365": 50.0}, "37": {"n": 1060, "valor": 395, "pct365": 41.7},
    "10": {"n": 1827, "valor": 395, "pct365": 37.4}, "06": {"n": 1140, "valor": 395, "pct365": 38.2},
    "39": {"n": 3364, "valor": 396, "pct365": 38.2}, "48": {"n": 553,  "valor": 397, "pct365": 36.2},
    "09": {"n": 466,  "valor": 397, "pct365": 37.1}, "41": {"n": 214,  "valor": 397, "pct365": 42.5},
    "20": {"n": 995,  "valor": 398, "pct365": 34.8}, "34": {"n": 110,  "valor": 398, "pct365": 35.5},
    "27": {"n": 223,  "valor": 399, "pct365": 33.6}, "24": {"n": 91,   "valor": 401, "pct365": 34.1},
    "31": {"n": 13,   "valor": 401, "pct365": 30.8}, "13": {"n": 49,   "valor": 403, "pct365": 32.7},
    "11": {"n": 165,  "valor": 407, "pct365": 29.1}, "42": {"n": 133,  "valor": 409, "pct365": 29.3},
    "05": {"n": 972,  "valor": 410, "pct365": 33.0}, "29": {"n": 44,   "valor": 412, "pct365": 38.6},
    "21": {"n": 69,   "valor": 417, "pct365": 21.7}, "50": {"n": 16,   "valor": 432, "pct365": 12.5},
    "26": {"n": 14,   "valor": 439, "pct365": 14.3},
}

# CCAA -> códigos INE de provincia que la componen (para el drill-down: clic
# en una CCAA del mapa -> filtra el nivel provincia a solo sus provincias).
CCAA_TO_PROV_CODES = {
    "País Vasco": ["01", "20", "48"],
    "Cantabria": ["39"],
    "Asturias": ["33"],
    "Galicia": ["15", "27", "32", "36"],
    "Castilla y León": ["05", "09", "24", "34", "37", "40", "42", "47", "49"],
    "Extremadura": ["06", "10"],
    "Andalucía": ["11", "14", "21", "29", "41"],
    "Castilla-La Mancha": ["02", "13", "19", "45"],
    "Madrid": ["28"],
    "Aragón": ["22", "44", "50"],
    "Cataluña": ["08", "17", "25"],
    "La Rioja": ["26"],
    "Navarra": ["31"],
    "C. Valenciana": ["12"],
}

# Inverso de CCAA_TO_PROV_CODES — para poder decir "esta provincia pertenece
# a esta CCAA" en las recomendaciones cuando se está a nivel provincia.
PROV_CODE_TO_CCAA = {code: ccaa for ccaa, codes in CCAA_TO_PROV_CODES.items() for code in codes}

METRIC_META = {
    "paricion": {
        "label": "Índice de parición",
        "unit": "%",
        "higher_is_better": True,
        "colorscale": "Purples",
        "low_n_threshold": 100,
        "low_n_unit": "hembras en edad reproductiva",
        "axis_label": "Índice de parición (%)",
        "hover_value_label": "Índice de parición",
        "value_suffix": "%",
        "n_label": "Hembras en edad reproductiva",
    },
    "interparto": {
        "label": "Espacio interpartos",
        "unit": " días",
        "higher_is_better": False,
        "colorscale": "Teal_r",
        "low_n_threshold": 100,
        "low_n_unit": "intervalos medidos",
        "axis_label": "Intervalo entre partos (días)",
        "hover_value_label": "Intervalo entre partos",
        "value_suffix": " días",
        "n_label": "Intervalos medidos",
    },
}

GRANULARITIES = {
    "ccaa": {
        "label": "Comunidad Autónoma",
        "unit_label": "CCAA",
        "geojson_url": CCAA_GEOJSON_URL,
        "id_field": "canon_name",
        "data": {"paricion": PARICION_CCAA_2025, "interparto": INTERPARTO_CCAA_2025},
        "name_of": lambda key: key,
    },
    "provincia": {
        "label": "Provincia",
        "unit_label": "provincia",
        "geojson_url": PROV_GEOJSON_URL,
        "id_field": "cod_prov",
        "data": {"paricion": PARICION_PROV_2025, "interparto": INTERPARTO_PROV_2025},
        "name_of": lambda key: PROVINCIA_NAME.get(key, key),
    },
}


@st.cache_data(show_spinner=False)
def load_geojson(gran_key: str):
    import geopandas as gpd

    gran = GRANULARITIES[gran_key]
    data = json.loads(urllib.request.urlopen(gran["geojson_url"], timeout=20).read())
    gdf = gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")
    gdf["geometry"] = gdf.geometry.buffer(0).simplify(0.01)
    if gran_key == "ccaa":
        gdf["canon_name"] = gdf["name"].map(CCAA_NAME_MAP)
        gdf = gdf[gdf["name"] != "Canarias"]
    else:
        # A nivel provincia Canarias son 2 provincias sueltas ("Las Palmas",
        # "Santa Cruz De Tenerife"), no una única "Canarias" — hay que
        # excluirlas por nombre o inflan muchísimo la extensión fija del
        # mapa (quedaría media España + islas a 1.500km al oeste).
        gdf = gdf[~gdf["name"].isin(["Las Palmas", "Santa Cruz De Tenerife"])]
    return json.loads(gdf.to_json())


@st.cache_data(show_spinner=False)
def geo_bounds(gran_key: str):
    """Extensión geográfica fija (toda España para ese nivel), calculada UNA
    vez sobre el geojson completo — no depende de qué esté seleccionado o
    filtrado, para que el mapa nunca cambie de zoom/encuadre al filtrar."""
    import geopandas as gpd

    geojson = load_geojson(gran_key)
    gdf = gpd.GeoDataFrame.from_features(geojson["features"], crs="EPSG:4326")
    minx, miny, maxx, maxy = gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    return (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)


def all_units(gran_key: str, metric_key: str) -> list[str]:
    gran = GRANULARITIES[gran_key]
    return sorted(gran["data"][metric_key].keys(), key=lambda k: gran["name_of"](k))


def build_metric_df(gran_key: str, metric_key: str, selected_keys: list[str] | None = None) -> pd.DataFrame:
    gran = GRANULARITIES[gran_key]
    rows = []
    for key, v in gran["data"][metric_key].items():
        if selected_keys is not None and key not in selected_keys:
            continue
        row = {"key": key, "name": gran["name_of"](key), "valor": v["valor"], "n": v["n"]}
        if "pct365" in v:
            row["pct_365"] = v["pct365"]
        rows.append(row)
    return pd.DataFrame(rows)


def render_interactive_map(gran_key: str, metric_key: str, selected_keys: list[str]) -> go.Figure:
    gran = GRANULARITIES[gran_key]
    cfg = METRIC_META[metric_key]
    df = build_metric_df(gran_key, metric_key, selected_keys)
    geojson = load_geojson(gran_key)

    fig = go.Figure()
    if len(df):
        custom_cols = ["name", "n"] + (["pct_365"] if "pct_365" in df else [])
        hover_extra = f"<br>{cfg['n_label']}: %{{customdata[1]}}"
        if "pct_365" in df:
            hover_extra += "<br>%% partos &lt;365 días: %{customdata[2]}%"
        fig.add_trace(go.Choropleth(
            geojson=geojson, locations=df["key"], featureidkey=f"properties.{gran['id_field']}",
            z=df["valor"], colorscale=cfg["colorscale"], marker_line_color="#fcfcfb", marker_line_width=0.8,
            colorbar=dict(title=cfg["unit"], thickness=14, len=0.75),
            customdata=df[custom_cols].values,
            hovertemplate="<b>%{customdata[0]}</b><br>" + cfg["hover_value_label"] + ": %{z:.1f}" + cfg["value_suffix"]
            + hover_extra + "<extra></extra>",
        ))
    # El resto de CCAA/provincias con dato pero fuera del filtro manual
    # actual también en gris, para completar la silueta de España (pedido
    # explícito: que se vea el país entero, no solo las regiones filtradas
    # flotando sueltas) — con un hover distinto a las que no tienen dato.
    all_keys = list(GRANULARITIES[gran_key]["data"][metric_key].keys())
    excluded = [k for k in all_keys if k not in (selected_keys or [])]
    if excluded:
        fig.add_trace(go.Choropleth(
            geojson=geojson, locations=excluded, featureidkey=f"properties.{gran['id_field']}",
            z=[0] * len(excluded), showscale=False,
            colorscale=[[0, NO_DATA_COLOR], [1, NO_DATA_COLOR]],
            marker_line_color="#fcfcfb", marker_line_width=0.8,
            hovertemplate="<b>%{location}</b><br>fuera del filtro<extra></extra>",
        ))

    # Regiones del geojson SIN dato alguno (sin ganaderías Limousin ahí),
    # también en gris pero con un aviso explícito distinto.
    feature_ids = [f["properties"].get(gran["id_field"]) for f in geojson["features"]]
    no_data = [fid for fid in feature_ids if fid is not None and fid not in all_keys]
    if no_data:
        fig.add_trace(go.Choropleth(
            geojson=geojson, locations=no_data, featureidkey=f"properties.{gran['id_field']}",
            z=[0] * len(no_data), showscale=False,
            colorscale=[[0, NO_DATA_COLOR], [1, NO_DATA_COLOR]],
            marker_line_color="#fcfcfb", marker_line_width=0.8,
            hovertemplate="<b>%{location}</b><br>Sin datos (sin ganaderías Limousin)<extra></extra>",
        ))

    # Extensión SIEMPRE fija a toda España para este nivel (no depende de la
    # selección/filtro actual), para que el mapa no cambie de zoom al filtrar.
    lon_min, lon_max, lat_min, lat_max = geo_bounds(gran_key)
    fig.update_geos(
        visible=False, bgcolor="rgba(0,0,0,0)", projection_type="mercator",
        lonaxis_range=[lon_min, lon_max], lataxis_range=[lat_min, lat_max],
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        height=VIS_HEIGHT,
    )
    return fig


def render_ranking_chart(gran_key: str, metric_key: str, selected_keys: list[str]) -> go.Figure:
    cfg = METRIC_META[metric_key]
    df = build_metric_df(gran_key, metric_key, selected_keys).sort_values("valor", ascending=not cfg["higher_is_better"])
    if not len(df):
        return go.Figure()
    df["label"] = df.apply(lambda r: f"{r['name']} *" if r["n"] < cfg["low_n_threshold"] else r["name"], axis=1)
    df["text"] = df["valor"].apply(lambda v: f"{v:.1f}{cfg['unit']}")

    fig = px.bar(
        df, x="valor", y="label", orientation="h",
        color="valor", color_continuous_scale=cfg["colorscale"],
        text="text",
    )
    fig.update_traces(
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>" + cfg["axis_label"] + ": %{x}<extra></extra>",
    )
    # El % (o los días) de las barras más largas se salía del área del
    # gráfico y quedaba cortado por el borde. En vez de "autorange=reversed"
    # (que ajusta el rango justo al máximo, sin margen para el texto), se fija
    # un rango explícito con un 18% de aire extra por encima del máximo —
    # dar el rango como [alto, bajo] invierte el eje igual que autorange.
    max_val = df["valor"].max()
    fig.update_layout(
        showlegend=False, coloraxis_showscale=False,
        margin=dict(l=30, r=10, t=10, b=0),
        # Invertido: el eje de categorías queda a la derecha y las barras
        # crecen hacia la izquierda (en vez del horizontal-bar estándar).
        yaxis=dict(title="", autorange="reversed", side="right"),
        xaxis=dict(title=cfg["axis_label"], range=[max_val * 1.18, 0]),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=max(VIS_HEIGHT, 26 * len(df)),
    )
    if metric_key == "interparto":
        fig.add_vline(x=365, line_dash="dash", line_color="#4a2d8f", annotation_text="365 días")
    return fig


def compute_kpis(gran_key: str = "ccaa", selected_keys: list[str] | None = None) -> dict:
    """KPIs sobre el ámbito activo: España entera (gran_key='ccaa', sin
    filtro) o una o varias CCAA agregando sus provincias (gran_key='provincia'
    con el filtro por CCAA activo). selected_keys filtra las claves de ese nivel."""
    gran = GRANULARITIES[gran_key]
    p_data = gran["data"]["paricion"]
    i_data = gran["data"]["interparto"]
    if selected_keys is not None:
        p_data = {k: v for k, v in p_data.items() if k in selected_keys}
        i_data = {k: v for k, v in i_data.items() if k in selected_keys}

    p = pd.DataFrame([{"key": k, "name": gran["name_of"](k), **v} for k, v in p_data.items()])
    i = pd.DataFrame([{"key": k, "name": gran["name_of"](k), **v} for k, v in i_data.items()])

    paricion_media = (p["valor"] * p["n"]).sum() / p["n"].sum() if len(p) else None
    mejor_paricion = p.loc[p["valor"].idxmax()] if len(p) else None
    interparto_medio = (i["valor"] * i["n"]).sum() / i["n"].sum() if len(i) else None
    mejor_interparto = i.loc[i["valor"].idxmin()] if len(i) else None

    return {
        "paricion_media": paricion_media,
        "mejor_paricion": mejor_paricion,
        "interparto_medio": interparto_medio,
        "mejor_interparto": mejor_interparto,
        "total_hembras": int(p["n"].sum()) if len(p) else 0,
        "unit_label": gran["unit_label"].capitalize(),
    }


def _con_ccaa(name: str, key: str, gran_key: str) -> str:
    """Nombre de la región, con su CCAA entre paréntesis si estamos a nivel
    provincia — relaciona la escala provincia/CCAA en la misma frase."""
    if gran_key == "provincia":
        ccaa = PROV_CODE_TO_CCAA.get(key)
        if ccaa and ccaa != name:  # evita "La Rioja (La Rioja)" en CCAA uniprovinciales
            return f"{name} ({ccaa})"
    return name


def compute_reco_facts(gran_key: str, selected_keys: list[str], offset: int = 0) -> list[dict]:
    """Calcula los 3 hechos verificados del panel de Recomendaciones — ver
    docs/prompt_recomendaciones_panel.md. 100% determinista: la IA (si se
    usa) solo redacta estos hechos, nunca decide cuál es la peor región ni
    en qué tramo cae — así no puede repetir el error de versiones
    anteriores (llamar "problema" a un valor que en realidad es aceptable).
    `offset` rota qué puesto (2º/3º peor, etc.) se usa en cada bloque, para
    dar variedad real al refrescar sin tocar los hechos de fondo."""
    df_p = build_metric_df(gran_key, "paricion", selected_keys)
    df_p = df_p[df_p["n"] >= 10]
    df_i = build_metric_df(gran_key, "interparto", selected_keys)
    df_i = df_i[df_i["n"] >= 10]

    facts = []

    if len(df_i) >= 1:
        df_i_sorted = df_i.sort_values("valor", ascending=False)  # peor (más días) primero
        idx1 = offset % len(df_i_sorted)
        peor1 = df_i_sorted.iloc[idx1]
        if peor1["valor"] > 450:
            tramo1 = "candidata_descarte"
        elif peor1["valor"] > 400:
            tramo1 = "pierde_productividad"
        else:
            tramo1 = "aceptable"
        facts.append({
            "tipo": "descarte_manejo", "region": peor1["name"], "key": peor1["key"],
            "valor": float(peor1["valor"]), "n": int(peor1["n"]),
            "pct_365": float(peor1["pct_365"]) if "pct_365" in peor1 and pd.notna(peor1["pct_365"]) else None,
            "tramo": tramo1,
        })
        if len(df_i_sorted) >= 2:
            idx2 = (idx1 + 1) % len(df_i_sorted)
            if idx2 == idx1:
                idx2 = (idx1 + 1) % len(df_i_sorted)
            peor2 = df_i_sorted.iloc[idx2]
            facts.append({
                "tipo": "vigilar_manejo", "region": peor2["name"], "key": peor2["key"],
                "valor": float(peor2["valor"]), "n": int(peor2["n"]),
                "pct_365": float(peor2["pct_365"]) if "pct_365" in peor2 and pd.notna(peor2["pct_365"]) else None,
            })

    if len(df_p) >= 2:
        df_p_sorted = df_p.sort_values("valor", ascending=True)  # peor (más bajo) primero
        idx3 = offset % len(df_p_sorted)
        peor_p = df_p_sorted.iloc[idx3]
        mejor_p = df_p.loc[df_p["valor"].idxmax()]
        facts.append({
            "tipo": "revisar_cubricion",
            "region_peor": peor_p["name"], "key_peor": peor_p["key"],
            "valor_peor": float(peor_p["valor"]), "n_peor": int(peor_p["n"]),
            "region_mejor": mejor_p["name"], "key_mejor": mejor_p["key"], "valor_mejor": float(mejor_p["valor"]),
        })

    # A nivel CCAA, añade un vistazo a nivel provincia dentro de la peor CCAA
    # de parición — más profundidad cruzando escalas, no solo CCAA sueltas.
    if gran_key == "ccaa" and len(df_p) >= 1:
        peor_ccaa = df_p.loc[df_p["valor"].idxmin()]
        prov_codes = set(CCAA_TO_PROV_CODES.get(peor_ccaa["name"], []))
        df_prov_ccaa = pd.DataFrame([
            {"key": code, "name": PROVINCIA_NAME.get(code, code), **PARICION_PROV_2025[code]}
            for code in prov_codes if code in PARICION_PROV_2025 and PARICION_PROV_2025[code]["n"] >= 10
        ])
        if len(df_prov_ccaa) >= 1:
            peor_prov = df_prov_ccaa.loc[df_prov_ccaa["valor"].idxmin()]
            facts.append({
                "tipo": "detalle_provincia",
                "region_ccaa": peor_ccaa["name"], "region_prov": peor_prov["name"], "key_prov": peor_prov["key"],
                "valor_ccaa": float(peor_ccaa["valor"]), "valor_prov": float(peor_prov["valor"]), "n_prov": int(peor_prov["n"]),
            })

    # Región líder en parición (rota con offset entre las 3 mejores, para
    # que el refresco cambie de verdad) y cómo le va en interpartos — tono
    # de aprendizaje/benchmark, no solo problemas.
    if len(df_p) >= 1:
        df_p_best_sorted = df_p.sort_values("valor", ascending=False)
        idx_lider = offset % min(3, len(df_p_best_sorted))
        lider_p = df_p_best_sorted.iloc[idx_lider]
        lider_i = GRANULARITIES[gran_key]["data"]["interparto"].get(lider_p["key"])
        facts.append({
            "tipo": "aprender_lider",
            "region": lider_p["name"], "key": lider_p["key"],
            "valor_paricion": float(lider_p["valor"]), "n": int(lider_p["n"]),
            "valor_interparto": float(lider_i["valor"]) if lider_i else None,
        })

    return facts[:5]


def _ganaderias_de(name: str, key: str, gran_key: str) -> str:
    """"ganaderías Limousin de X" (sin artículo — cada frase antepone "Las"
    o "las" según toque) en vez de hablar de la región como entidad, para
    dejar claro que hablamos de las explotaciones ganaderas del tenant, no
    de la comunidad/provincia como administración."""
    return f"ganaderías Limousin de {_con_ccaa(name, key, gran_key)}"


def render_facts_deterministico(facts: list[dict], gran_key: str) -> list[str]:
    """Redacción 100% Python (sin LLM) de los hechos de compute_reco_facts,
    en el estilo aprobado (ver docs/prompt_recomendaciones_panel.md) —
    fallback siempre disponible si la IA no responde. Cada bloque sigue la
    estructura análisis (dato) → conclusión (qué significa) → recomendación
    (qué hacer), con longitud variable: no todos los bloques necesitan las
    3 partes igual de largas."""
    # El nivel (CCAA/provincia) ya se indica una vez en el subtítulo del
    # panel — no hace falta repetirlo en cada frase.
    out = []
    for f in facts:
        if f["tipo"] == "descarte_manejo":
            ganaderias = _ganaderias_de(f["region"], f["key"], gran_key)
            pct_txt = f" y un **{f['pct_365']:.1f}%** de intervalos menores a 365 días" if f["pct_365"] is not None else ""
            if f["tramo"] == "candidata_descarte":
                out.append(
                    f"🔴 Las {ganaderias} registran el intervalo entre partos más largo del conjunto: "
                    f"**{f['valor']:.0f} días**{pct_txt}. Al superar los 450 días, sus vacas entran en el rango de "
                    f"repetidora crónica, donde el cálculo económico cambia — mantenerlas a la espera de que "
                    f"vuelvan a parir puede no compensar frente a su valor de venta como animal de abasto. "
                    f"**Recomendación:** revisar caso a caso si conviene descartar o dar una última oportunidad "
                    f"con seguimiento reforzado."
                )
            elif f["tramo"] == "pierde_productividad":
                out.append(
                    f"🟠 Las {ganaderias} tienen un intervalo de **{f['valor']:.0f} días**{pct_txt}, ya por encima "
                    f"del objetivo de 365. En este tramo (400-450 días) las vacas siguen siendo productivas pero "
                    f"darán menos terneros a lo largo de su vida que con un ciclo anual, con el mismo coste de "
                    f"mantenimiento. **Recomendación:** vigilar de cerca el manejo reproductivo antes de que "
                    f"escale a candidata a descarte."
                )
            else:
                out.append(
                    f"✅ El intervalo entre partos más largo de este conjunto está en las {ganaderias} "
                    f"(**{f['valor']:.0f} días**{pct_txt}), todavía dentro de un rango aceptable, sin alarma de "
                    f"descarte por ahora."
                )
        elif f["tipo"] == "vigilar_manejo":
            ganaderias = _ganaderias_de(f["region"], f["key"], gran_key)
            pct_txt = f" y un **{f['pct_365']:.1f}%** de intervalos menores a 365 días" if f["pct_365"] is not None else ""
            out.append(
                f"👀 Vigilar el manejo posparto en las {ganaderias}, que tienen un intervalo de "
                f"**{f['valor']:.0f} días**{pct_txt}, lo que sugiere una oportunidad de mejora en nutrición y "
                f"sanidad para acortar el intervalo entre partos."
            )
        elif f["tipo"] == "revisar_cubricion":
            ganaderias_peor = _ganaderias_de(f["region_peor"], f["key_peor"], gran_key)
            ganaderias_mejor = _ganaderias_de(f["region_mejor"], f["key_mejor"], gran_key)
            gap = f["valor_mejor"] - f["valor_peor"]
            out.append(
                f"🎯 Las {ganaderias_peor} paren solo el **{f['valor_peor']:.1f}%** de sus nodrizas al año, frente "
                f"al **{f['valor_mejor']:.1f}%** de las {ganaderias_mejor} — **{gap:.1f} puntos** de diferencia "
                f"(n={f['n_peor']}). Cada vaca que no pare sigue comiendo y ocupando pasto sin generar ningún "
                f"ingreso ese año: es el mayor punto de fuga de rentabilidad de la cría extensiva. "
                f"**Recomendación:** revisar la estrategia de cubrición y fertilidad (nutrición pre-cubrición, "
                f"genética, sanidad) antes de invertir en otros KPI."
            )
        elif f["tipo"] == "detalle_provincia":
            ccaa_nombre = f["region_ccaa"]
            out.append(
                f"🔍 Bajando a nivel provincia dentro de {ccaa_nombre} (**{f['valor_ccaa']:.1f}%** de parición): "
                f"la provincia que más arrastra el dato es **{f['region_prov']}** (**{f['valor_prov']:.1f}%**, "
                f"n={f['n_prov']}) — ahí es donde priorizar el seguimiento, no en toda la comunidad por igual."
            )
        elif f["tipo"] == "aprender_lider":
            # Bloque corto e informativo (2 líneas) a propósito — para
            # rellenar el hueco tras los análisis largos de arriba, sin
            # forzar el mismo nivel de razonamiento en todos los bloques.
            ganaderias = _ganaderias_de(f["region"], f["key"], gran_key)
            if f["valor_interparto"] is not None:
                out.append(
                    f"🏆 Las {ganaderias} lideran la parición (**{f['valor_paricion']:.1f}%**) y también rinden bien "
                    f"en interpartos (**{f['valor_interparto']:.0f} días**) — referencia a estudiar."
                )
            else:
                out.append(f"🏆 Las {ganaderias} lideran la parición con un **{f['valor_paricion']:.1f}%** — referencia a estudiar.")
    return out


RECO_AI_ANGLES = [
    "prioriza qué región necesita intervención más urgente en intervalo entre partos",
    "prioriza dónde está el mayor margen de mejora en índice de parición frente al líder",
    "prioriza qué región lidera y qué patrón de manejo podría explicarlo",
    "cruza ambos análisis (parición e interpartos) para señalar una región con un problema compuesto en ambos KPI",
]


def generate_ai_recommendations_v2(gran_key: str, view_context: str, offset: int = 0) -> list[str] | None:
    """La IA busca ELLA MISMA en las tablas completas (ya incluidas en el
    system prompt de build_context) qué regiones destacar — a diferencia de
    phrase_facts_with_ai, aquí decide, no solo redacta. El prompt exacto
    depende de _current_model_tier() — docs/prompts/recomendaciones_prompt_
    small_model.md (con guardas extra) o _large_model.md (más simple), ver
    docs/prompts/README.md. Devuelve None si no hay clave, el gate de
    contención bloquea, la llamada falla, o la respuesta no parece válida —
    la UI cae entonces a render_facts_deterministico(), que nunca alucina."""
    if not _current_provider_has_key():
        return None
    nivel_txt = "por provincia" if gran_key == "provincia" else "por comunidad autónoma"
    variante = RECO_AI_ANGLES[offset % len(RECO_AI_ANGLES)]
    tier = _current_model_tier()
    template = _load_prompt_md(f"recomendaciones_prompt_{tier}_model.md")
    prompt = template.format(nivel_txt=nivel_txt, variante=variante)
    try:
        answer = call_llm([{"role": "user", "content": prompt}], view_context, temperature=0.5)
    except Exception:
        return None
    if answer.startswith("⚠️") or answer.startswith("⏳"):
        return None
    lines = [l.strip(" -•").strip() for l in answer.splitlines() if l.strip(" -•").strip()]
    return lines[:3] if len(lines) >= 2 else None


def phrase_facts_with_ai(facts: list[dict], gran_key: str, view_context: str) -> list[str] | None:
    """La IA redacta (no decide) los hechos ya verificados — ver
    docs/prompt_recomendaciones_panel.md. Devuelve None si no hay clave, si
    el gate de contención bloquea, o si la llamada falla — la UI cae
    entonces a render_facts_deterministico()."""
    if not _current_provider_has_key():
        return None
    deterministico = render_facts_deterministico(facts, gran_key)
    if not deterministico:
        return None
    hechos_txt = "\n".join(f"{i+1}. {frase}" for i, frase in enumerate(deterministico))
    prompt = (
        "Tienes estas 3 frases YA VERIFICADAS y correctas (no cambies ningún dato, región, cifra ni "
        "gravedad — están calculadas por reglas de negocio fiables, tu única tarea es mejorar la redacción "
        "para que suene más natural, variando el estilo entre frases):\n"
        f"{hechos_txt}\n\n"
        "Devuelve exactamente 3 frases reescritas, una por línea, con '- ' al principio de cada línea, "
        "sin numerarlas, sin introducción ni cierre. Cada una debe seguir empezando por el tipo de acción "
        "(descarte/revisión, vigilar manejo, revisar estrategia) y citar las mismas cifras exactas."
    )
    try:
        answer = call_llm([{"role": "user", "content": prompt}], view_context, temperature=0.4)
    except Exception:
        return None
    if answer.startswith("⚠️") or answer.startswith("⏳"):
        return None
    lines = [l.strip(" -•").strip() for l in answer.splitlines() if l.strip(" -•").strip()]
    return lines[:3] if len(lines) >= 2 else None


def generate_recommendations(gran_key: str, metric_key: str, selected_keys: list[str], angle_idx: int = 0) -> list[str]:
    """3 recomendaciones independientes (descarte/manejo, vigilancia,
    estrategia de cubrición), cada una sobre una región distinta cuando los
    datos lo permiten — combina parición e interpartos sin depender de cuál
    esté seleccionada en "Análisis". 100% determinista (ver
    compute_reco_facts/render_facts_deterministico); el llamador puede
    intentar antes phrase_facts_with_ai() sobre los mismos hechos."""
    facts = compute_reco_facts(gran_key, selected_keys, offset=angle_idx)
    if not facts:
        return ["No hay suficientes regiones con muestra fiable en este filtro para generar recomendaciones."]
    return render_facts_deterministico(facts, gran_key)


# ---------------------------------------------------------------- IA conversacional ("Limusin GPT")
def build_context(view_context: str = "", filtered_table: str = "") -> str:
    rows_ccaa = []
    for ccaa in sorted(set(PARICION_CCAA_2025) | set(INTERPARTO_CCAA_2025)):
        p = PARICION_CCAA_2025.get(ccaa, {})
        i = INTERPARTO_CCAA_2025.get(ccaa, {})
        rows_ccaa.append({
            "ccaa": ccaa,
            "indice_paricion_pct": p.get("valor"), "n_hembras": p.get("n"),
            "intervalo_dias": i.get("valor"), "pct_menos_365d": i.get("pct365"), "n_intervalos": i.get("n"),
        })
    df_ccaa = pd.DataFrame(rows_ccaa)

    rows_prov = []
    for code in sorted(set(PARICION_PROV_2025) | set(INTERPARTO_PROV_2025)):
        p = PARICION_PROV_2025.get(code, {})
        i = INTERPARTO_PROV_2025.get(code, {})
        rows_prov.append({
            "provincia": PROVINCIA_NAME.get(code, code),
            "indice_paricion_pct": p.get("valor"), "n_hembras": p.get("n"),
            "intervalo_dias": i.get("valor"), "pct_menos_365d": i.get("pct365"), "n_intervalos": i.get("n"),
        })
    df_prov = pd.DataFrame(rows_prov)

    comunes = df_ccaa.dropna(subset=["indice_paricion_pct", "intervalo_dias"])
    corr = comunes["indice_paricion_pct"].corr(comunes["intervalo_dias"]) if len(comunes) >= 3 else None
    corr_txt = f"{corr:.2f}" if corr is not None else "n/d"

    filtro_bloque = f"""
SUBCONJUNTO QUE EL USUARIO TIENE FILTRADO AHORA MISMO EN EL PANEL — si la
pregunta no nombra una región concreta, responde SOBRE ESTO, no sobre España
entera:
{filtered_table}
""" if filtered_table else ""

    vista_bloque = (
        f"VISTA ACTUAL DEL USUARIO EN EL PANEL (para preguntas ambiguas tipo "
        f'"¿cómo vamos aquí?" o "y esto qué tal"): {view_context}.'
    ) if view_context else ""

    template = _load_prompt_md("limusin_gpt_system_prompt.md")
    return template.format(
        df_ccaa=df_ccaa.to_string(index=False),
        df_prov=df_prov.to_string(index=False),
        corr_txt=corr_txt,
        filtro_bloque=filtro_bloque,
        vista_bloque=vista_bloque,
    )


# ---------------------------------------------------------------- freno de
# peticiones a la IA: existió como gate propio (5s entre peticiones, 10/min)
# para proteger la cuota GRATUITA de Groq de ráfagas. Desactivado desde que
# Gemini es el proveedor por defecto (2026-08-18) — resultaba demasiado
# restrictivo para uso normal en Streamlit Cloud en vivo, y Gemini es un
# recurso de pago con su propio rate limit en servidor (que call_llm ya
# captura y convierte en aviso legible vía el try/except de más abajo). Se
# deja la infraestructura (lock/estado/constantes) por si hiciera falta
# reactivar un límite de gasto en el futuro — basta con hacer que
# _llm_rate_gate() vuelva a evaluar las condiciones en vez de retornar None.
_LLM_LOCK = threading.Lock()
_LLM_STATE = {"last_call_ts": 0.0, "call_times": []}
LLM_MIN_INTERVAL_SECONDS = 5   # sin efecto mientras _llm_rate_gate esté desactivado
LLM_MAX_CALLS_PER_MINUTE = 10  # sin efecto mientras _llm_rate_gate esté desactivado


def _llm_rate_gate() -> str | None:
    """Desactivado — ver comentario de arriba. Devuelve siempre None (vía
    libre) en vez de bloquear peticiones."""
    return None


def _current_model_tier() -> str:
    """"small" o "large" según el modelo activo (AI_PROVIDER + GROQ_MODEL/
    ANTHROPIC_MODEL/GEMINI_MODEL) contra MODEL_TIERS — ver
    docs/prompts/README.md. Cualquier modelo no listado cae en "small"
    (más prudente)."""
    if AI_PROVIDER == "groq":
        modelo = GROQ_MODEL
    elif AI_PROVIDER == "gemini":
        modelo = GEMINI_MODEL
    else:
        modelo = ANTHROPIC_MODEL
    return MODEL_TIERS.get(modelo, "small")


def _current_provider_has_key() -> bool:
    """Si el proveedor de IA activo (AI_PROVIDER) tiene su clave configurada."""
    if AI_PROVIDER == "groq":
        return bool(GROQ_API_KEY)
    if AI_PROVIDER == "gemini":
        return bool(GEMINI_API_KEY)
    return bool(ANTHROPIC_API_KEY)


@st.cache_data(show_spinner=False)
def _load_prompt_md(filename: str) -> str:
    """Lee un prompt de docs/prompts/ del disco (cacheado). Si el archivo no
    existe (p.ej. un despliegue que no incluya docs/), usa un texto mínimo
    de emergencia en vez de romper la app."""
    path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Responde de forma breve, precisa y basada solo en los datos indicados arriba, sin inventar cifras."


def call_llm(messages: list, view_context: str = "", filtered_table: str = "", temperature: float = 0.2) -> str:
    """Nunca lanza excepción — cualquier fallo de la API (rate limit, timeout,
    clave inválida...) se convierte en un mensaje de aviso legible, para que
    ni el chat ni el panel de Recomendaciones puedan tumbar la app entera."""
    gate_msg = _llm_rate_gate()
    if gate_msg:
        return gate_msg
    system_prompt = build_context(view_context, filtered_table)
    try:
        if AI_PROVIDER == "groq":
            if not GROQ_API_KEY:
                return "⚠️ Falta configurar `GROQ_API_KEY` en `.env` para poder usar Limusin GPT."
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            completion = client.chat.completions.create(
                model=GROQ_MODEL, max_tokens=350, temperature=temperature,
                messages=[{"role": "system", "content": system_prompt}] + messages,
            )
            return completion.choices[0].message.content
        elif AI_PROVIDER == "anthropic":
            if not ANTHROPIC_API_KEY:
                return "⚠️ Falta configurar `ANTHROPIC_API_KEY` en `.env` para poder usar Limusin GPT."
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            message = client.messages.create(
                model=ANTHROPIC_MODEL, max_tokens=350, temperature=temperature,
                system=system_prompt, messages=messages,
            )
            return message.content[0].text
        elif AI_PROVIDER == "gemini":
            if not GEMINI_API_KEY:
                return "⚠️ Falta configurar `GEMINI_API_KEY` en `.env` para poder usar Limusin GPT."
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            gemini_contents = [
                {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in messages
            ]
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=gemini_contents,
                config=types.GenerateContentConfig(
                    # Los modelos Gemini recientes (3.6) gastan una parte
                    # GRANDE del presupuesto de tokens en "pensamiento"
                    # interno antes de la respuesta visible — en pruebas
                    # reales, ~2200 tokens de pensamiento para el prompt de
                    # Recomendaciones. Con 350-1000 (lo que basta para
                    # Groq/Anthropic, que no "piensan") la respuesta salía
                    # vacía o cortada a media frase. 4000 da margen de
                    # sobra para pensamiento + la respuesta completa.
                    system_instruction=system_prompt, temperature=temperature, max_output_tokens=4000,
                ),
            )
            return response.text or "⚠️ La IA no devolvió texto (respuesta vacía). Prueba de nuevo."
        return f"⚠️ AI_PROVIDER desconocido: {AI_PROVIDER!r}"
    except Exception as e:
        err_name = type(e).__name__
        err_txt = str(e)
        if "RateLimit" in err_name or "429" in err_txt or "RESOURCE_EXHAUSTED" in err_txt:
            return ("⚠️ Límite de peticiones a la IA alcanzado por ahora (cuota limitada por minuto). "
                     "Espera un momento y vuelve a preguntar.")
        return f"⚠️ No se pudo contactar con la IA ahora mismo ({err_name}). Prueba de nuevo en un momento."



# ---------------------------------------------------------------- página
st.set_page_config(page_title="Limousin España — Panel regional", page_icon="🐄", layout="wide")


@st.cache_data(show_spinner=False)
def _logo_b64() -> str:
    import base64
    if not os.path.exists(LOGO_PATH):
        return ""
    with open(LOGO_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


st.markdown(f"""
<style>
    .block-container {{ padding-top: 1rem; padding-bottom: 1rem; max-width: 100% !important; }}
    #MainMenu, footer, header[data-testid="stHeader"] {{ visibility: hidden; height: 0; }}
    section[data-testid="stSidebar"] {{ display: none; }}

    .lim-header {{
        display: flex; align-items: center; gap: 18px;
        background: linear-gradient(135deg, #ffffff 0%, #f3f6ec 100%);
        border: 1px solid #e7e5df; border-radius: 16px;
        padding: 8px 22px; margin-bottom: 10px;
    }}
    .lim-header img {{ height: 40px; width: auto; flex-shrink: 0; }}
    .lim-header-title {{ font-size: 1.4rem; font-weight: 800; color: {INK}; line-height: 1.15; }}
    .lim-header-sub {{ color: {MUTED}; font-size: 0.85rem; margin-top: 2px; }}

    .lim-kpi-row {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 10px; }}
    .lim-kpi {{
        background: #ffffff; border: 1px solid #e7e5df; border-left: 4px solid {BRAND_GREEN};
        border-radius: 12px; padding: 8px 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }}
    .lim-kpi.accent-purple {{ border-left-color: #7554bd; }}
    .lim-kpi.accent-teal {{ border-left-color: #1f8a7a; }}
    .lim-kpi-icon {{ font-size: 1.1rem; }}
    .lim-kpi-label {{ color: {MUTED}; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.02em; }}
    .lim-kpi-value {{ color: {INK}; font-size: 1.35rem; font-weight: 800; margin-top: 1px; }}
    .lim-kpi-delta {{ color: #1f8a3a; font-size: 0.8rem; font-weight: 600; margin-top: 1px; }}

    .lim-card {{
        background: #ffffff; border: 1px solid #e7e5df; border-radius: 14px;
        padding: 10px 20px 6px; margin-bottom: 8px;
    }}
    .lim-card-title {{ font-size: 1.05rem; font-weight: 700; color: {INK}; margin-bottom: 2px; }}
    .lim-card-sub {{ color: {MUTED}; font-size: 0.8rem; margin-bottom: 6px; }}

    .lim-gpt-card {{
        background: linear-gradient(180deg, #fffdf7 0%, #ffffff 55%); border: 1px solid #e7e5df;
        border-radius: 16px; padding: 16px 18px; height: 100%;
    }}
    .lim-gpt-title {{
        font-weight: 800; font-size: 1.15rem; color: {INK};
        display: flex; align-items: center; gap: 8px; margin-bottom: 2px;
    }}
    .lim-badge {{
        display: inline-block; background: {BRAND_GREEN}; color: #fff;
        border-radius: 999px; padding: 1px 10px; font-size: 0.68rem; font-weight: 700;
    }}
    .lim-reco-item {{
        background: #ffffff; border: 1px solid #e7e5df; border-left: 3px solid {BRAND_GREEN};
        border-radius: 10px; padding: 8px 10px; margin-bottom: 8px;
        font-size: 0.82rem; line-height: 1.35; color: {INK};
    }}
    div[data-testid="stChatInput"] textarea {{ background: #fff; }}
    button[data-testid="stBaseButton-secondary"] {{
        border-radius: 6px !important; font-size: 0.72rem !important; padding: 1px 8px !important;
        min-height: 1.6rem !important; text-align: left !important; white-space: normal !important;
    }}

    div[data-baseweb="radio"] label {{ font-weight: 600; }}
    hr {{ margin: 0.5rem 0 0.9rem; }}
</style>
""", unsafe_allow_html=True)

logo_b64 = _logo_b64()
st.markdown(f"""
<div class="lim-header">
    {f'<img src="data:image/png;base64,{logo_b64}"/>' if logo_b64 else ''}
    <div>
        <div class="lim-header-title">Limousin España — panel regional</div>
        <div class="lim-header-sub">Índice de parición y espacio interpartos, por CCAA o por provincia · <b>año natural 2025</b></div>
    </div>
</div>
""", unsafe_allow_html=True)

# ---- Reserva visual del bloque de KPIs (se rellena más abajo, tras
# calcular gran_key/selected_keys a partir de los controles, pero debe
# aparecer ANTES que los controles en la página).
kpi_slot = st.container()

# ---- Controles: análisis + nivel (vista general por CCAA o por provincia)
# + filtro (SIEMPRE por Comunidad Autónoma, sea cual sea el nivel elegido).
# Filtrar por una o varias CCAA fuerza la vista a provincias, mostrando la
# unión de las provincias de las CCAA seleccionadas (p.ej. Andalucía +
# Extremadura -> provincias de ambas). El clic en el mapa (a nivel CCAA)
# hace lo mismo que seleccionar esa CCAA a mano en el filtro.
ALL_CCAA_NAMES = sorted(CCAA_TO_PROV_CODES.keys())

col_metric, col_gran, col_filter, col_drill = st.columns([1, 1, 1.6, 1.2])
with col_metric:
    metric_label_to_key = {v["label"]: k for k, v in METRIC_META.items()}
    selected_label = st.selectbox("Análisis", list(metric_label_to_key.keys()))
    metric_key = metric_label_to_key[selected_label]
with col_gran:
    gran_label_to_key = {v["label"]: k for k, v in GRANULARITIES.items()}
    nivel_label = st.selectbox("Nivel (vista general)", list(gran_label_to_key.keys()), key="nivel_radio")
    nivel_key = gran_label_to_key[nivel_label]
with col_filter:
    ccaa_filter = st.multiselect(
        "Filtrar por Comunidad Autónoma",
        options=ALL_CCAA_NAMES,
        placeholder="Todas",
        key="ccaa_filter",
    )

if ccaa_filter:
    # Filtro activo: se ve SIEMPRE por provincia, con la unión de provincias
    # de las CCAA elegidas, sin importar lo que diga "Nivel".
    gran_key = "provincia"
    gran = GRANULARITIES[gran_key]
    units = all_units(gran_key, metric_key)
    prov_codes = set()
    for c in ccaa_filter:
        prov_codes |= set(CCAA_TO_PROV_CODES.get(c, []))
    selected_keys = [k for k in units if k in prov_codes] or units
else:
    gran_key = nivel_key
    gran = GRANULARITIES[gran_key]
    units = all_units(gran_key, metric_key)
    selected_keys = units

with col_drill:
    if ccaa_filter:
        st.write("")
        st.markdown(f"📍 Provincias de: **{', '.join(ccaa_filter)}**")
        if st.button("✕ Quitar filtro y volver a España"):
            st.session_state["ccaa_filter"] = []
            st.rerun()

all_names = [gran["name_of"](k) for k in units]

# ---- KPIs: dinámicos según el ámbito activo (España, o las CCAA
# seleccionadas en el filtro, agregando sus provincias).
if ccaa_filter:
    kpi_scope_label = f"Ámbito: {', '.join(ccaa_filter)} (por provincia)"
    kpis = compute_kpis("provincia", selected_keys)
elif gran_key == "provincia":
    kpi_scope_label = "Ámbito: España (por provincia)"
    kpis = compute_kpis("provincia", None)
else:
    kpi_scope_label = "Ámbito: España (por CCAA)"
    kpis = compute_kpis("ccaa", None)

unit_lbl = kpis["unit_label"]
with kpi_slot:
    st.caption(kpi_scope_label)
    st.markdown(f"""
<div class="lim-kpi-row">
    <div class="lim-kpi accent-purple">
        <div class="lim-kpi-label"><span class="lim-kpi-icon">🎯</span> Índice de parición medio</div>
        <div class="lim-kpi-value">{f"{kpis['paricion_media']:.1f}%" if kpis['paricion_media'] is not None else "—"}</div>
    </div>
    <div class="lim-kpi accent-purple">
        <div class="lim-kpi-label"><span class="lim-kpi-icon">🏆</span> Mejor {unit_lbl} (parición)</div>
        <div class="lim-kpi-value">{kpis['mejor_paricion']['name'] if kpis['mejor_paricion'] is not None else "—"}</div>
        <div class="lim-kpi-delta">{f"↑ {kpis['mejor_paricion']['valor']:.1f}%" if kpis['mejor_paricion'] is not None else ""}</div>
    </div>
    <div class="lim-kpi accent-teal">
        <div class="lim-kpi-label"><span class="lim-kpi-icon">⏱️</span> Intervalo entre partos medio</div>
        <div class="lim-kpi-value">{f"{kpis['interparto_medio']:.0f} días" if kpis['interparto_medio'] is not None else "—"}</div>
    </div>
    <div class="lim-kpi accent-teal">
        <div class="lim-kpi-label"><span class="lim-kpi-icon">🏆</span> Mejor {unit_lbl} (interpartos)</div>
        <div class="lim-kpi-value">{kpis['mejor_interparto']['name'] if kpis['mejor_interparto'] is not None else "—"}</div>
        <div class="lim-kpi-delta">{f"↑ {kpis['mejor_interparto']['valor']:.0f} días" if kpis['mejor_interparto'] is not None else ""}</div>
    </div>
    <div class="lim-kpi">
        <div class="lim-kpi-label"><span class="lim-kpi-icon">🐄</span> Nodrizas analizadas</div>
        <div class="lim-kpi-value">{kpis['total_hembras']:,}</div>
    </div>
</div>
""", unsafe_allow_html=True)

cfg = METRIC_META[metric_key]

# ---- Ranking (izquierda) + mapa (centro, más grande) PEGADOS + panel de
# Recomendaciones (en el hueco donde antes vivía Limusin GPT) + Limusin GPT
# como sidebar plegable en el lateral derecho (botón para abrir/cerrar).
# Mapa, ranking y las tarjetas laterales comparten la misma altura real
# (VIS_HEIGHT), sin contenedores de altura fija anidados (eso causaba scroll
# con hueco en blanco) — cada elemento define su propia altura y ya salen
# igualados. La columna del mapa/ranking predomina en anchura.
def _toggle_gpt_open():
    # Callback de on_click en vez del patrón manual "if button: set + rerun()"
    # — el callback se ejecuta y actualiza session_state ANTES de que
    # Streamlit decida el layout de la siguiente pasada, evitando el efecto
    # de quedarse "colado" que puede darse con el rerun manual.
    st.session_state["gpt_open"] = not st.session_state.get("gpt_open", True)


gpt_open = st.session_state.get("gpt_open", True)
if gpt_open:
    col_main, col_reco, col_toggle, col_gpt = st.columns([3.3, 1, 0.2, 1.3], gap="small")
else:
    col_main, col_reco, col_toggle = st.columns([3.3, 1, 0.2], gap="small")
    col_gpt = None

with col_main:
    st.markdown('<div class="lim-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="lim-card-title">{cfg["label"]} por {gran["label"].lower()}</div>', unsafe_allow_html=True)
    subtitle = f'{len(selected_keys)}/{len(units)} {gran["unit_label"]}s · año natural 2025'
    if gran_key == "ccaa":
        subtitle += " · haz clic en una comunidad del mapa para ver sus provincias"
    st.markdown(f'<div class="lim-card-sub">{subtitle}</div>', unsafe_allow_html=True)

    col_rank, col_map = st.columns([1, 1.6], gap="medium")
    with col_rank:
        st.markdown("**📊 Ranking**")
        # Con muchas filas (p.ej. las 39 provincias de España sin filtrar) el
        # ranking se alargaría mucho más que el mapa y rompería la extensión
        # de la vista. Se limita a VIS_HEIGHT con scroll interno; con pocas
        # filas no llega a necesitar scroll y se ve igual que antes. Al
        # cambiar de filtro, al ser un contenedor nuevo, el scroll siempre
        # vuelve a arriba (vista por defecto).
        with st.container(height=VIS_HEIGHT):
            st.plotly_chart(render_ranking_chart(gran_key, metric_key, selected_keys), width="stretch")
    with col_map:
        st.markdown("**🗺️ Distribución**")
        map_state = st.plotly_chart(
            render_interactive_map(gran_key, metric_key, selected_keys), width="stretch",
            config={"scrollZoom": False, "displayModeBar": False},
            key="map_plot", on_select="rerun", selection_mode=("points",),
        )

    st.caption(f"* Muestra pequeña (&lt; {cfg['low_n_threshold']} {cfg['low_n_unit']}): tomar con cautela. "
               "Gris: fuera del filtro o sin ganaderías Limousin. Fuente: Datos propios Ixorigue.")
    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("📋 Ver tabla de datos"):
        df_show = build_metric_df(gran_key, metric_key, selected_keys).drop(columns=["key"]).rename(columns={
            "name": gran["unit_label"].capitalize(), "valor": cfg["axis_label"], "n": cfg["n_label"],
            "pct_365": "% partos <365 días",
        }).set_index(gran["unit_label"].capitalize())
        st.dataframe(df_show, width="stretch")

# ---- Panel de Recomendaciones: ocupa el hueco donde antes vivía Limusin
# GPT. 100% deterministas (generate_recommendations, sin llamar al LLM): el
# usuario prefirió este formato conciso con emojis/negrita frente a las
# versiones generadas por IA, que además con el modelo pequeño (necesario
# para no agotar la cuota gratuita) a veces señalaban una región equivocada
# como "la peor". El botón de refresco rota el ángulo del análisis (3
# variantes), instantáneo y sin ningún riesgo de rate limit.
with col_reco:
    st.markdown('<div class="lim-gpt-card">', unsafe_allow_html=True)
    title_col, refresh_col = st.columns([3, 1])
    with title_col:
        st.markdown('<div class="lim-gpt-title">📌 Recomendaciones</div>', unsafe_allow_html=True)
    with refresh_col:
        refresh_clicked = st.button("🔄", key="refresh_reco", help="Refrescar con otro enfoque")

    reco_angle = st.session_state.get("reco_angle", 0)
    if refresh_clicked:
        reco_angle = (reco_angle + 1) % 3
        st.session_state["reco_angle"] = reco_angle

    st.caption(f"Basadas en los datos que estás viendo ahora mismo ({gran['label'].lower()}) · conclusiones de Limusin GPT.")
    with st.container(height=VIS_HEIGHT):
        # 3 bloques independientes — el usuario pidió expresamente que sea
        # la IA quien busque y decida (generate_ai_recommendations_v2), no
        # solo que redacte hechos ya fijados. Con un modelo "small" (ver
        # docs/prompts/README.md) se restringe a nivel CCAA: en pruebas
        # reales acertó 5/6 a nivel CCAA (11 filas) pero solo 1/3 a nivel
        # provincia (39 filas) — llegó a inventar una provincia que ni está
        # en los datos. Con un modelo "large" no hace falta esa restricción.
        ia_permitida = gran_key == "ccaa" or _current_model_tier() == "large"
        view_desc = f"{kpi_scope_label}; análisis mostrado: {cfg['label']}"
        frases = generate_ai_recommendations_v2(gran_key, view_desc, offset=reco_angle) if ia_permitida else None
        if not frases:
            facts = compute_reco_facts(gran_key, selected_keys, offset=reco_angle)
            frases = render_facts_deterministico(facts, gran_key)
        frases = frases[:3] if frases else ["No hay suficientes regiones con muestra fiable en este filtro para generar recomendaciones."]
        for reco in frases:
            reco_html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", reco)
            st.markdown(f'<div class="lim-reco-item">{reco_html}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ---- Botón para abrir/cerrar Limusin GPT como sidebar lateral.
with col_toggle:
    st.write("")
    st.write("")
    st.button(
        "◂" if gpt_open else "💬", key="toggle_gpt", help="Mostrar/ocultar Limusin GPT",
        use_container_width=True, on_click=_toggle_gpt_open,
    )

# Clic en una CCAA del mapa (solo tiene sentido en nivel CCAA, sin filtro
# activo) -> equivale a seleccionarla a mano en "Filtrar por Comunidad
# Autónoma": fuerza la vista a sus provincias.
if gran_key == "ccaa" and map_state and map_state.get("selection", {}).get("points"):
    pt = map_state["selection"]["points"][0]
    clicked_name = (pt.get("customdata") or [None])[0]
    if clicked_name and clicked_name in CCAA_TO_PROV_CODES and [clicked_name] != ccaa_filter:
        st.session_state["ccaa_filter"] = [clicked_name]
        st.rerun()

if col_gpt is not None:
    with col_gpt:
        st.markdown('<div class="lim-gpt-card">', unsafe_allow_html=True)
        st.markdown('<div class="lim-gpt-title">🐮 Limusin GPT <span class="lim-badge">BETA</span></div>', unsafe_allow_html=True)
        st.caption("Agente IA especializado en producción de ganaderías cárnicas.")

        if "limusin_chat" not in st.session_state:
            st.session_state.limusin_chat = []

        SUGGESTIONS = [
            "¿Diferencia Aragón/Cataluña?",
            "¿Qué provincia pare más?",
            "¿Relación parición-interpartos?",
        ]
        clicked = None

        # Misma altura que el mapa/ranking (VIS_HEIGHT), para que las tres
        # columnas queden visualmente igualadas sin envolver en un contenedor
        # de altura fija adicional (eso es lo que causaba el scroll en blanco).
        chat_box = st.container(height=VIS_HEIGHT)
        with chat_box:
            if not st.session_state.limusin_chat:
                st.chat_message("assistant").write(
                    "Pregúntame sobre el índice de parición o el espacio interpartos, "
                    "por Comunidad Autónoma o por provincia, año 2025."
                )
                # Los chips solo aparecen antes del primer mensaje, DENTRO de la
                # cajetilla de chat (pegados abajo del todo) — en cuanto se
                # pregunta otra cosa, desaparecen (ya no se cumple la condición).
                for s in SUGGESTIONS:
                    if st.button(s, key=f"chip_{s}", use_container_width=True):
                        clicked = s
            for msg in st.session_state.limusin_chat:
                st.chat_message(msg["role"]).write(msg["content"])

        prompt = st.chat_input("Pregunta a Limusin GPT...") or clicked
        if prompt:
            st.session_state.limusin_chat.append({"role": "user", "content": prompt})
            with chat_box:
                st.chat_message("user").write(prompt)
                with st.chat_message("assistant"):
                    with st.spinner("Limusin GPT está pensando..."):
                        current_view_desc = f"{kpi_scope_label}; análisis mostrado: {cfg['label']}"
                        filtered_table = ""
                        if ccaa_filter:
                            sub_df = build_metric_df(gran_key, metric_key, selected_keys).drop(columns=["key"])
                            filtered_table = sub_df.to_string(index=False)
                        answer = call_llm(st.session_state.limusin_chat, current_view_desc, filtered_table)
                    st.write(answer)
            st.session_state.limusin_chat.append({"role": "assistant", "content": answer})
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
