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
import time
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
    GROQ_API_KEY,
    GROQ_MODEL,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO_PATH = os.path.join(REPO_ROOT, "Logo_ixorigue-BpQt6KE7.png")
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


def generate_recommendations(gran_key: str, metric_key: str, selected_keys: list[str], angle_idx: int = 0) -> list[str]:
    """2-3 recomendaciones en forma de frase fluida (redacción de consultor,
    no bullets con emoji) basadas en los datos reales del ámbito activo —
    deterministas (sin LLM: nunca alucinan, son instantáneas y no dependen
    de la disponibilidad ni de la cuota de Groq/Anthropic). El ángulo
    (0/1/2) varía el enfoque para que el botón de refrescar dé variedad
    real sin necesitar una llamada a la IA."""
    cfg = METRIC_META[metric_key]
    df = build_metric_df(gran_key, metric_key, selected_keys)
    df = df[df["n"] >= 10]  # descarta muestras demasiado pequeñas para recomendar sobre ellas
    if len(df) < 2:
        return ["No hay suficientes regiones con muestra fiable en este filtro para generar recomendaciones."]

    if cfg["higher_is_better"]:
        worst, best = df.loc[df["valor"].idxmin()], df.loc[df["valor"].idxmax()]
    else:
        worst, best = df.loc[df["valor"].idxmax()], df.loc[df["valor"].idxmin()]
    unit = GRANULARITIES[gran_key]["unit_label"]
    es_paricion = metric_key == "paricion"
    fmt = (lambda v: f"{v:.1f}%") if es_paricion else (lambda v: f"{v:.0f} días")
    # "un 74,5%" tiene sentido en español, pero "un 384 días" no — para
    # interpartos hace falta el sustantivo ("un intervalo de 384 días").
    frase_valor = (lambda v: f"un {fmt(v)}") if es_paricion else (lambda v: f"un intervalo de {fmt(v)}")

    def gap_fmt(v: float) -> str:
        if es_paricion:
            return f"{v:.1f} puntos"
        dias = round(v)
        return f"{dias} día" if dias == 1 else f"{dias} días"

    def con_ccaa(row) -> str:
        """Nombre de la región, con su CCAA entre paréntesis si estamos a
        nivel provincia — para relacionar la escala provincia/CCAA en la
        misma frase, no solo el nombre suelto."""
        if gran_key == "provincia":
            ccaa = PROV_CODE_TO_CCAA.get(row["key"])
            if ccaa and ccaa != row["name"]:  # evita "La Rioja (La Rioja)" en CCAA uniprovinciales
                return f"{row['name']} ({ccaa})"
        return row["name"]

    def otro_analisis(row, contexto: str = "peor") -> str | None:
        """Cruza el otro análisis (parición <-> interpartos) para la misma
        región — diagnóstico conjunto en vez de mirar un solo KPI suelto.
        contexto="peor" (diagnóstico de un problema) o "mejor" (¿el liderazgo
        se sostiene en todo el ciclo o es solo en este KPI?)."""
        other_key = "interparto" if es_paricion else "paricion"
        other_data = GRANULARITIES[gran_key]["data"][other_key].get(row["key"])
        if not other_data:
            return None
        other_cfg = METRIC_META[other_key]
        other_fmt = (lambda v: f"{v:.1f}%") if other_key == "paricion" else (lambda v: f"{v:.0f} días")
        other_val = other_data["valor"]
        also_bad = other_val < 60 if other_key == "paricion" else other_val > 400
        also_good = other_val >= 70 if other_key == "paricion" else other_val <= 395

        if contexto == "peor":
            if also_bad:
                return (
                    f"El problema no parece limitarse a {cfg['label'].lower()}: su {other_cfg['label'].lower()} "
                    f"también es preocupante ({other_fmt(other_val)}), señal de que la fertilidad y la reconcepción "
                    f"posparto fallan a la vez, no un único eslabón del proceso."
                )
            return (
                f"En cambio, su {other_cfg['label'].lower()} ({other_fmt(other_val)}) está dentro de rango razonable, "
                f"así que el problema parece limitarse a este KPI concreto y no a todo el ciclo reproductivo."
            )
        else:  # contexto == "mejor"
            if also_good:
                return (
                    f"Su buen resultado no se limita a {cfg['label'].lower()}: el {other_cfg['label'].lower()} "
                    f"({other_fmt(other_val)}) también acompaña, señal de que el manejo funciona bien en todo el "
                    f"ciclo reproductivo, no solo en este KPI."
                )
            return (
                f"Sin embargo, su {other_cfg['label'].lower()} ({other_fmt(other_val)}) no acompaña al mismo nivel, "
                f"así que el liderazgo se apoya en un único KPI, no en todo el ciclo reproductivo."
            )

    angle = angle_idx % 3
    recos = []

    if angle == 0:
        # Peor región + diagnóstico + margen con la mejor, en una sola frase.
        gap = abs(best["valor"] - worst["valor"])
        if es_paricion:
            recos.append(
                f"La región de {con_ccaa(worst)}, con un índice de parición del {fmt(worst['valor'])}, requiere "
                f"intervención urgente para mejorar su fertilidad y cubrición inicial, ya que se encuentra "
                f"{gap_fmt(gap)} por debajo del líder {con_ccaa(best)}, que tiene un índice de parición del {fmt(best['valor'])}."
            )
        else:
            recos.append(
                f"La región de {con_ccaa(worst)}, con un intervalo entre partos de {fmt(worst['valor'])}, debería "
                f"revisar la reconcepción posparto de sus vacas (nutrición, sanidad), ya que supera en "
                f"{gap_fmt(gap)} al líder {con_ccaa(best)}, que registra un intervalo de {fmt(best['valor'])}."
            )
        cruce = otro_analisis(worst)
        if cruce:
            recos.append(cruce)
        umbral = 60 if es_paricion else 420
        alarm = df[df["valor"] < umbral] if es_paricion else df[df["valor"] > umbral]
        if len(alarm):
            names = ", ".join(alarm.sort_values("valor", ascending=es_paricion)["name"].head(3))
            cond = f"por debajo del {umbral}% de parición" if es_paricion else f"por encima de los {umbral} días de intervalo"
            recos.append(f"Actualmente hay {len(alarm)} {unit}(s) {cond} ({names}), lo que apunta a un problema extendido, no aislado en una sola región.")
        else:
            cond = f"del {umbral}% de parición" if es_paricion else f"de los {umbral} días de intervalo"
            recos.append(f"Ninguna región de este conjunto está por {'debajo' if es_paricion else 'encima'} {cond}, así que no hay una alarma grave y generalizada por este KPI.")

    elif angle == 1:
        # Quién lidera, qué tan cerca está el segundo puesto, y si lo es también en el otro análisis.
        df_by_best = df.sort_values("valor", ascending=not cfg["higher_is_better"])
        second = df_by_best.iloc[1]
        gap2 = abs(best["valor"] - second["valor"])
        recos.append(
            f"{con_ccaa(best)} lidera con {frase_valor(best['valor'])} (n={int(best['n'])}), lo que la convierte en "
            f"referencia para entender qué se está haciendo mejor en manejo, cubrición o nutrición."
        )
        recos.append(
            f"Le sigue {con_ccaa(second)}, con {frase_valor(second['valor'])} — solo {gap_fmt(gap2)} de diferencia — lo que "
            f"sugiere que el buen resultado de {best['name']} no es un caso aislado, sino un patrón que se repite en la zona."
        )
        cruce = otro_analisis(best, contexto="mejor")
        if cruce:
            recos.append(cruce)
        else:
            reliability = "una muestra amplia, dato fiable para tomarlo como benchmark del sector" if best["n"] >= 500 else "una muestra moderada, conviene contrastarlo antes de generalizarlo"
            recos.append(f"Con n={int(best['n'])} hembras analizadas en {best['name']}, se trata de {reliability}.")

    else:
        # Patrones de fiabilidad: tamaño de muestra vs. resultado, y valor típico del conjunto.
        corr = df["n"].corr(df["valor"])
        # El signo de "corr" es sobre el valor crudo; para interpartos un valor
        # más alto es PEOR (higher_is_better=False), así que hay que invertir
        # el signo antes de hablar de "rendir mejor/peor" en términos de negocio.
        corr_hacia_mejor = corr if cfg["higher_is_better"] else -corr
        if corr_hacia_mejor is not None and corr_hacia_mejor > 0.2:
            lectura = "positiva: las regiones con más nodrizas analizadas tienden a rendir mejor, probablemente porque son explotaciones más consolidadas"
        elif corr_hacia_mejor is not None and corr_hacia_mejor < -0.2:
            lectura = "negativa: las regiones con más nodrizas analizadas tienden a rendir peor, señal de que el tamaño no garantiza mejor manejo"
        else:
            lectura = "prácticamente nula: el tamaño de la ganadería no explica por sí solo el resultado, hay que mirar el manejo caso a caso"
        recos.append(f"La correlación entre el tamaño de muestra y {cfg['label'].lower()} es de {corr:.2f} — {lectura}.")
        small = df[df["n"] < 100]
        if len(small):
            names = ", ".join(small.sort_values("n")["name"].head(3))
            recos.append(f"{len(small)} {unit}(s) tienen una muestra reducida (menos de 100): {names} — sus cifras deben tomarse con cautela antes de sacar conclusiones firmes.")
        else:
            recos.append(f"Todas las regiones de este conjunto tienen una muestra de al menos 100 — los datos son razonablemente sólidos para comparar entre sí.")
        mid = df["valor"].median()
        recos.append(f"El valor típico del conjunto se sitúa en torno al {fmt(mid)}, con {con_ccaa(best)} y {con_ccaa(worst)} marcando los dos extremos.")

    return recos[:3]


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

    return f"""Eres "Limusin GPT", un agente especializado en ganadería de
carne en modo empresa y productividad: piensas como un consultor de negocio
para producción de vacuno de carne, modelo de cría con vaca nodriza
(cow-calf, razas tipo Limousin). No eres un lector de tablas: interpretas
los números como lo haría un consultor que ayuda a un ganadero a tomar
decisiones — en qué franja/provincia hay margen de mejora, y qué
implicación de negocio tiene cada cifra (una vaca que no pare es un año
entero de coste de mantenimiento sin ingreso; un intervalo entre partos
largo es menos terneros vendidos a lo largo de la vida productiva del mismo
animal, con igual coste anual).

DATOS POR COMUNIDAD AUTÓNOMA (año natural 2025):
{df_ccaa.to_string(index=False)}

DATOS POR PROVINCIA (año natural 2025):
{df_prov.to_string(index=False)}

ESTOS DOS BLOQUES DE DATOS SON TU ÚNICA FUENTE DE VERDAD, NO HAY NINGÚN OTRO
DATO DISPONIBLE (ni municipios, ni ganaderías individuales, ni otros años, ni
tasa de nacidos vivos, ni supervivencia al destete, ni peso al destete —
esos otros KPI del embudo de productividad NO están en estos datos, así que
si preguntan por ellos di explícitamente que no los tienes).

Columnas:
- indice_paricion_pct: % de nodrizas en edad reproductiva (≥18 meses) que
  parieron en 2025. Más alto es mejor — es el mayor punto de fuga de
  rentabilidad en cría extensiva, porque una vaca que no pare sigue comiendo
  y ocupando pasto sin generar ningún ingreso ese año.
- n_hembras: nº de nodrizas en edad reproductiva usadas como denominador.
- intervalo_dias: días medios entre parto y parto consecutivo de la misma
  vaca, para partos que cerraron en 2025. <365 = pare todos los años
  (óptimo); 365-400 = aceptable; >400-420 = ya pierde terneros a lo largo de
  su vida productiva con el mismo coste anual; >450-500 días o repetidora
  crónica = candidata a descarte/venta, deja de compensar mantenerla.
- pct_menos_365d: % de esos intervalos que fueron ≤365 días.
- n_intervalos: nº de intervalos medidos (tamaño de muestra del intervalo).
- NaN / vacío: sin dato fiable (muestra insuficiente) — no te lo inventes.

Correlación (Pearson) entre índice de parición e intervalo entre partos a
nivel CCAA: r = {corr_txt}.
{filtro_bloque}
{f"VISTA ACTUAL DEL USUARIO EN EL PANEL (para preguntas ambiguas tipo \"¿cómo vamos aquí?\" o \"y esto qué tal\"): {view_context}." if view_context else ""}

REGLAS PARA RESPONDER (que no alucines es lo más importante):
1. SOLO puedes usar los números de estos datos. Si te preguntan algo que no
   está aquí (hectáreas, sanidad, pesos, sementales, municipios, otras
   razas, otros años, nacidos vivos, supervivencia al destete...), responde
   explícitamente "no tengo ese dato" en vez de estimar, inventar o
   extrapolar un número que suene plausible.
2. Nunca inventes una cifra decimal que no esté literalmente en los datos.
   Si necesitas calcular algo (una diferencia, una media, un ratio), muestra
   la cuenta con los números reales.
3. Si el n de una región es bajo (menos de 100 hembras/intervalos, o menos
   de 20-30 a nivel provincia), avisa de que el dato es poco fiable antes de
   sacar conclusiones fuertes sobre ella.
4. Cuando compares dos regiones, da los dos números exactos y la diferencia,
   no solo una valoración cualitativa. Usa los datos por provincia si
   preguntan por una provincia, o por comunidad autónoma si preguntan por
   una CCAA — pero NUNCA dirijas al usuario a "la tabla 1" o "la tabla 2" ni
   menciones esos nombres internos; habla de "los datos por comunidad
   autónoma" o "por provincia" con naturalidad, como lo haría un consultor.
4bis. IMPORTANTE — comparaciones con regiones sin dato: si te piden comparar
   una región que NO aparece en los datos (ninguna fila, ni NaN — sencillamente
   no existe: p.ej. Murcia, Ceuta, Melilla, Baleares, Canarias a nivel CCAA, o
   cualquier provincia que no esté en el listado), NO inventes un número ni
   la des por buena "sin dato". Dilo explícitamente: no se puede comparar
   porque no hay ganaderías Limousin con datos en esa comunidad/provincia, así
   que comparar contra otra sería injusto/sin base. Después ofrece una
   alternativa: pregunta si quiere que sugieras tú una comparación con una
   región similar que sí tenga dato (o sugiere una directamente si es obvia
   por tamaño de muestra o cercanía geográfica), en vez de dejar la
   conversación en un callejón sin salida.
5. Explica en lenguaje llano y directo, sin jerga estadística innecesaria —
   pero sin perder rigor técnico: cada análisis debe conectar el número con
   su implicación de negocio (coste, rentabilidad, decisión sobre el
   rebaño), no quedarse en "el valor es X".
6. Si el usuario pregunta algo ambiguo sin nombrar una región concreta
   (p.ej. "¿cómo vamos aquí?", "y esto qué tal", "analiza esto"), interpreta
   que se refiere al SUBCONJUNTO FILTRADO o a la VISTA ACTUAL DEL PANEL
   indicados arriba (si los hay), no a España entera.
7. Cuando te pidan un análisis, sé HOLÍSTICO — no reportes una métrica sola
   ni una región suelta, busca patrones y correlaciones en el conjunto:
   a. RELACIONA índice de parición e intervalo entre partos entre sí, porque
      diagnostican fallos DISTINTOS del mismo proceso: parición baja =
      problema de fertilidad/cubrición inicial; intervalo largo con
      parición aceptable = problema de reconcepción tras el parto
      (nutrición posparto, sanidad, manejo). Dos regiones pueden tener el
      mismo problema aparente por razones opuestas — señálalo cuando lo veas.
   b. Usa la correlación (r) entre parición e intervalo ya calculada arriba
      para hablar de la tendencia general, no solo de casos sueltos —
      indica si es fuerte/débil y qué significa en la práctica.
   c. Cruza el tamaño de muestra (n_hembras/n_intervalos) con los valores:
      ¿las regiones con más nodrizas (más consolidadas, más dato) tienden a
      rendir distinto que las de muestra pequeña? Adviértelo como patrón,
      no solo como advertencia de fiabilidad.
   d. Busca agrupaciones/outliers: ¿hay varias regiones parecidas que
      podrían compartir causa común (p.ej. mismo rango de intervalo, mismo
      nivel de parición) frente a una o dos que se salen claramente de la
      norma?
   e. Cierra siempre con qué le interesa a una ganadería de cría que busca
      optimizar su operativa: dónde está el margen de mejora real, qué
      patrón se repite entre regiones parecidas, y qué haría distinto una
      explotación con esos números — no una lista de datos, una conclusión.
8. Responde en español, tono directo de consultor, sin rodeos ni relleno.
   SÉ BREVE por defecto: 3-5 frases o 3-4 líneas en total (bullets cortos si
   ayudan), no un informe. Solo alárgate si el usuario pide explícitamente
   más detalle ("profundiza", "explícamelo mejor", "más análisis").
9. Eres Limusin GPT, un agente especializado ÚNICAMENTE en producción de
   ganadería cárnica y su productividad como negocio — no un chatbot
   generalista. Si te preguntan algo ajeno a esta materia (temas
   personales, otras industrias, opinión política, programar, o cualquier
   petición sin relación con parición, intervalo entre partos, productividad
   ganadera o los datos de este panel), no lo respondas: indica en una
   frase que estás especializado solo en el análisis de estos datos
   ganaderos y redirige la conversación hacia qué puedes analizar aquí.
"""


# ---------------------------------------------------------------- freno de
# peticiones a la IA: gates propios, independientes del rate limit real de
# Groq/Anthropic, para no gastar la cuota gratuita en ráfagas (varios
# visitantes a la vez, o clics repetidos en "🔄 Refrescar"). Estado a nivel
# de módulo (no de sesión) porque en Streamlit Cloud todas las sesiones de
# un mismo despliegue comparten el mismo proceso Python — el freno protege
# la cuota real, compartida por todos los visitantes.
_LLM_LOCK = threading.Lock()
_LLM_STATE = {"last_call_ts": 0.0, "call_times": []}
LLM_MIN_INTERVAL_SECONDS = 5   # espera mínima entre dos peticiones cualquiera
LLM_MAX_CALLS_PER_MINUTE = 10  # tope adicional en ráfaga


def _llm_rate_gate() -> str | None:
    """None si se puede proceder; si no, un mensaje de aviso ya listo para
    mostrar en vez de la respuesta de la IA."""
    now = time.time()
    with _LLM_LOCK:
        elapsed = now - _LLM_STATE["last_call_ts"]
        if elapsed < LLM_MIN_INTERVAL_SECONDS:
            wait = LLM_MIN_INTERVAL_SECONDS - elapsed
            return f"⏳ Espera {wait:.0f}s antes de la siguiente pregunta — protege la cuota gratuita de la IA."
        times = _LLM_STATE["call_times"]
        while times and now - times[0] > 60:
            times.pop(0)
        if len(times) >= LLM_MAX_CALLS_PER_MINUTE:
            return (f"⚠️ Demasiadas peticiones a la IA en el último minuto (límite propio de "
                     f"{LLM_MAX_CALLS_PER_MINUTE}/min para cuidar la cuota gratuita). Espera un poco.")
        _LLM_STATE["last_call_ts"] = now
        times.append(now)
        return None


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
        return f"⚠️ AI_PROVIDER desconocido: {AI_PROVIDER!r}"
    except Exception as e:
        err_name = type(e).__name__
        if "RateLimit" in err_name:
            return ("⚠️ Límite de peticiones a la IA alcanzado por ahora (la clave gratuita de Groq "
                     "tiene cuota limitada por minuto). Espera un momento y vuelve a preguntar.")
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
gpt_open = st.session_state.get("gpt_open", True)
if gpt_open:
    col_main, col_reco, col_toggle, col_gpt = st.columns([3.3, 1, 0.14, 1.3], gap="small")
else:
    col_main, col_reco, col_toggle = st.columns([3.3, 1, 0.14], gap="small")
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

    st.caption("Basadas en los datos que estás viendo ahora mismo.")
    with st.container(height=VIS_HEIGHT):
        for reco in generate_recommendations(gran_key, metric_key, selected_keys, reco_angle):
            reco_html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", reco)
            st.markdown(f'<div class="lim-reco-item">{reco_html}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ---- Botón para abrir/cerrar Limusin GPT como sidebar lateral.
with col_toggle:
    st.write("")
    st.write("")
    if st.button("◂" if gpt_open else "💬", key="toggle_gpt", help="Mostrar/ocultar Limusin GPT", use_container_width=True):
        st.session_state["gpt_open"] = not gpt_open
        st.rerun()

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
