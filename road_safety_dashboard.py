"""UK Road Safety Dashboard v2 - for council transport planners (DfT STATS19, 2025).

Run:    streamlit run road_safety_dashboard_v2.py
Needs:  road_safety_2025_merged.csv (24 columns, one row per collision) in the same folder
        .streamlit/config.toml (the dark road-sign theme; see config.toml)
Optional: lad_lookup.csv with columns  code,name  to show council names instead of ONS codes
Install:  pip install -U streamlit plotly pandas pydeck
"""
import html
import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots

try:
    import pydeck as pdk
except ImportError:  # pydeck ships with Streamlit, but stay safe
    pdk = None

DATA_FILE = "road_safety_2025_merged.csv"
LOOKUP_FILE = "lad_lookup.csv"

st.set_page_config(page_title="Britain's worst road collisions - 2025", page_icon="🚧",
                   layout="wide")

# ---------------------------- Design tokens ----------------------------
BG, PANEL, SIGN = "#0B1F3A", "#10294B", "#0E4C92"        # deep blue, panel, motorway-sign blue
INK, MUTED, GRID = "#F4F6F8", "#9FB3CF", "rgba(244,246,248,.12)"
YELLOW, URBAN = "#F7C600", "#6CB4FF"
SEV = {"Fatal": "#E5383B", "Serious": "#F29E1F", "Slight": "#3FA66B"}
HEAT = [[0, "#12325A"], [0.35, "#2E6FB7"], [0.7, "#F7C600"], [1, "#E5383B"]]
HEAD, BODY = "Overpass, 'Arial Narrow', sans-serif", "'Atkinson Hyperlegible', Arial, sans-serif"
CFG = {"displayModeBar": False}

# ------------------------ Code -> label lookups ------------------------
# Verify against the DfT data guide before submitting.
SEVERITY = {1: "Fatal", 2: "Serious", 3: "Slight"}
DAYS = {1: "Sunday", 2: "Monday", 3: "Tuesday", 4: "Wednesday",
        5: "Thursday", 6: "Friday", 7: "Saturday"}
WEEK_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEATHER = {1: "Fine", 2: "Raining", 3: "Snowing", 4: "Fine + high winds",
           5: "Raining + high winds", 6: "Snowing + high winds",
           7: "Fog or mist", 8: "Other"}
LIGHT = {1: "Daylight", 4: "Dark - lights lit", 5: "Dark - lights unlit",
         6: "Dark - no lighting", 7: "Dark - lighting unknown"}
LIGHT_GROUP = {"Daylight": "Daylight", "Dark - lights lit": "Dark, street lit",
               "Dark - lights unlit": "Dark, unlit or unknown",
               "Dark - no lighting": "Dark, unlit or unknown",
               "Dark - lighting unknown": "Dark, unlit or unknown"}
SURFACE = {1: "Dry", 2: "Wet or damp", 3: "Snow", 4: "Frost or ice",
           5: "Flood", 6: "Oil or diesel", 7: "Mud"}
AREA = {1: "Urban", 2: "Rural"}
ROAD_TYPE = {1: "Roundabout", 2: "One way street", 3: "Dual carriageway",
             6: "Single carriageway", 7: "Slip road", 12: "One way / slip road"}
CAS_CLASS = {1: "Driver or rider", 2: "Passenger", 3: "Pedestrian"}
VEH_GROUPS = {
    "Pedal cycle": [1],
    "Motorcycle": [2, 3, 4, 5, 23, 97, 103, 104, 105, 106],
    "Car or taxi": [8, 9, 108, 109],
    "Bus or minibus": [10, 11, 110],
    "Goods vehicle": [19, 20, 21, 98, 113],
}
VEH_LOOKUP = {c: g for g, codes in VEH_GROUPS.items() for c in codes}
VALID_SPEEDS = [20, 30, 40, 50, 60, 70]
DARK = ["Dark - lights lit", "Dark - lights unlit", "Dark - no lighting", "Dark - lighting unknown"]


# ------------------------------ Styling ------------------------------
def inject_css() -> None:
    st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Overpass:wght@600;800&display=swap');
html, body, .stApp, [data-testid="stAppViewContainer"] {{ background:{BG}; color:{INK}; font-family:{BODY}; }}
[data-testid="stHeader"] {{ background:transparent; }}
.block-container {{ padding-top:2rem; max-width:1400px; }}
h1,h2,h3,h4 {{ font-family:{HEAD}; letter-spacing:0; }}
section[data-testid="stSidebar"] {{ background:#081A33; border-right:4px dashed rgba(247,198,0,.55); }}
.hero h1 {{ font-weight:800; font-size:2.7rem; line-height:1.08; margin:0 0 .5rem; }}
.hero p {{ color:{MUTED}; font-size:1.08rem; max-width:64ch; margin:0; }}
.centreline {{ height:6px; margin:1.2rem 0 1.5rem; border-radius:3px;
  background:repeating-linear-gradient(90deg,#fff 0 34px,transparent 34px 62px);
  animation:draw 1.4s ease-out both; }}
@keyframes draw {{ from {{ clip-path:inset(0 100% 0 0); }} to {{ clip-path:inset(0 0 0 0); }} }}
.stTabs [data-baseweb="tab-list"] {{ gap:8px; border-bottom:3px dashed rgba(244,246,248,.30); padding-bottom:12px; flex-wrap:wrap; }}
.stTabs [data-baseweb="tab"] {{ height:auto; padding:8px 18px; border:2px solid rgba(244,246,248,.30);
  border-radius:10px; background:transparent; font-family:{HEAD}; font-weight:600;
  transition:background .2s, border-color .2s; }}
.stTabs [data-baseweb="tab"]:hover {{ border-color:#fff; }}
.stTabs [aria-selected="true"] {{ background:{SIGN}; border-color:#fff; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none; }}
.sec {{ margin:1.6rem 0 .4rem; }}
.sec h3 {{ margin:0 0 .25rem; font-size:1.45rem; font-weight:800; }}
.sec p {{ margin:0; color:{MUTED}; max-width:75ch; border-left:3px solid {YELLOW}; padding-left:.75rem; }}
.post {{ background:{SIGN}; border:3px solid #fff; border-radius:14px; padding:14px 18px; margin-bottom:12px;
  display:grid; grid-template-columns:52px 1.4fr 1fr 1fr; gap:6px 18px; align-items:center; }}
.post .rank {{ font-family:{HEAD}; font-weight:800; font-size:1.9rem; color:#0B1F3A; background:{YELLOW};
  width:44px; height:44px; border-radius:50%; display:flex; align-items:center; justify-content:center; }}
.post .pname {{ font-family:{HEAD}; font-weight:800; font-size:1.25rem; }}
.post .pstat b {{ font-family:{HEAD}; font-size:1.3rem; }}
.post .pwhy {{ grid-column:2 / -1; color:#D6E4F7; font-size:.92rem; }}
@media (max-width:760px) {{ .post {{ grid-template-columns:44px 1fr; }} .post .pwhy {{ grid-column:1 / -1; }} }}
@media (prefers-reduced-motion:reduce) {{ .centreline {{ animation:none; }} }}
</style>""", unsafe_allow_html=True)


def section(title: str, note: str = "") -> None:
    p = f"<p>{note}</p>" if note else ""
    st.markdown(f"<div class='sec'><h3>{title}</h3>{p}</div>", unsafe_allow_html=True)


def style(fig: go.Figure, h: int = 380, legend: bool = False) -> go.Figure:
    fig.update_layout(
        height=h, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=BODY, color=INK, size=13), margin=dict(l=8, r=8, t=24, b=8),
        hoverlabel=dict(bgcolor=SIGN, bordercolor="#fff", font=dict(family=BODY, color="#fff")),
        legend=dict(orientation="h", y=-0.18, bgcolor="rgba(0,0,0,0)"), showlegend=legend,
        transition=dict(duration=450, easing="cubic-in-out"))
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    return fig


def style_anim(fig: go.Figure) -> go.Figure:
    """Make Plotly's play button and slider readable on the dark theme."""
    if fig.layout.updatemenus:
        fig.layout.updatemenus[0].bgcolor = SIGN
        fig.layout.updatemenus[0].bordercolor = "#fff"
        fig.layout.updatemenus[0].font.color = "#fff"
        fig.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 650
        fig.layout.updatemenus[0].buttons[0].args[1]["transition"]["duration"] = 450
    if fig.layout.sliders:
        fig.layout.sliders[0].font.color = MUTED
        fig.layout.sliders[0].currentvalue.font.color = INK
        fig.layout.sliders[0].bgcolor = "rgba(255,255,255,.10)"
        fig.layout.sliders[0].activebgcolor = YELLOW
    return fig


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", config=CFG)


def hex_rgba(hex_color: str, a: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def kpi_strip(items: list) -> None:
    """The one orchestrated motion moment: figures count up once on load."""
    cells = ""
    for label, val, dec, sub, dot in items:
        cells += (f"<div class='k'><div class='n' data-v='{val}' data-d='{dec}'>0</div>"
                  f"<div class='l'><span class='dot' style='background:{dot}'></span>{label}</div>"
                  f"<div class='s'>{sub}</div></div>")
    doc = f"""<html><head><link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Overpass:wght@800&display=swap" rel="stylesheet">
<style>
body {{ margin:0; font-family:{BODY}; }}
.sign {{ display:flex; flex-wrap:wrap; background:{SIGN}; border:4px solid #fff; border-radius:16px; padding:18px 6px; color:#fff; }}
.k {{ flex:1 1 150px; text-align:center; padding:4px 10px; border-right:3px dashed rgba(255,255,255,.55); }}
.k:last-child {{ border-right:none; }}
.n {{ font-family:{HEAD}; font-weight:800; font-size:40px; line-height:1.1; font-variant-numeric:tabular-nums; }}
.l {{ font-weight:700; font-size:15px; margin-top:2px; }}
.dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:7px; border:1.5px solid #fff; }}
.s {{ font-size:12.5px; color:#CFE0F7; margin-top:2px; }}
@media (max-width:640px) {{ .k {{ border-right:none; flex-basis:45%; }} .n {{ font-size:30px; }} }}
</style></head><body><div class="sign">{cells}</div>
<script>
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
document.querySelectorAll('.n').forEach(el => {{
  const v = parseFloat(el.dataset.v), d = parseInt(el.dataset.d);
  const fmt = x => x.toLocaleString('en-GB', {{minimumFractionDigits:d, maximumFractionDigits:d}});
  if (reduce) {{ el.textContent = fmt(v); return; }}
  const t0 = performance.now(), dur = 1200;
  const tick = t => {{ const p = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3);
    el.textContent = fmt(v * e); if (p < 1) requestAnimationFrame(tick); }};
  requestAnimationFrame(tick);
}});
</script></body></html>"""
    if hasattr(st, "iframe"):          # newer Streamlit
        st.iframe(doc, height="content")
    else:                              # older Streamlit
        components.html(doc, height=150)


# ------------------------------- Data -------------------------------
@st.cache_data(show_spinner="Loading collisions...")
def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_FILE, low_memory=False)
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df["hour"] = pd.to_datetime(df["time"], format="%H:%M", errors="coerce").dt.hour
    df = df.dropna(subset=["date", "hour"]).copy()
    df["hour"] = df["hour"].astype(int)
    df["month_name"] = df["date"].dt.month.map(lambda m: MONTHS[m - 1])
    df["weekday"] = df["day_of_week"].map(DAYS)
    df["severity"] = df["collision_severity"].map(SEVERITY)
    df = df.dropna(subset=["severity"]).copy()
    df["is_ksi"] = df["severity"].isin(["Fatal", "Serious"])
    df["weather"] = df["weather_conditions"].map(WEATHER).fillna("Unknown")
    df["light"] = df["light_conditions"].map(LIGHT).fillna("Unknown")
    df["surface"] = df["road_surface_conditions"].map(SURFACE).fillna("Unknown")
    df["area"] = df["urban_or_rural_area"].map(AREA).fillna("Unknown")
    df["road"] = df["road_type"].map(ROAD_TYPE).fillna("Unknown")
    df["speed_limit"] = df["speed_limit"].where(df["speed_limit"].isin(VALID_SPEEDS))
    df["speed_label"] = df["speed_limit"].apply(lambda x: f"{int(x)} mph" if pd.notna(x) else np.nan)
    df["vehicle_group"] = df["vehicle_type"].map(VEH_LOOKUP).fillna("Other")
    df["driver_age"] = df["age_of_driver"].where(df["age_of_driver"] >= 0)
    df["driver_age_group"] = pd.cut(df["driver_age"], [-1, 24, 39, 59, 200],
                                    labels=["Under 25", "25-39", "40-59", "60+"])
    df["casualty_class_label"] = df["casualty_class"].map(CAS_CLASS).fillna("Unknown")
    df["casualty_age"] = df["age_of_casualty"].where(df["age_of_casualty"] >= 0)
    df["casualty_age_group"] = pd.cut(df["casualty_age"], [-1, 15, 24, 39, 59, 200],
                                      labels=["0-15", "16-24", "25-39", "40-59", "60+"])
    df.loc[~df["latitude"].between(49, 61), "latitude"] = np.nan
    df.loc[~df["longitude"].between(-9, 2), "longitude"] = np.nan
    code = df["local_authority_ons_district"].astype(str)
    df["district"] = code
    if os.path.exists(LOOKUP_FILE):
        lk = pd.read_csv(LOOKUP_FILE)
        lk.columns = [c.strip().lower() for c in lk.columns]
        if {"code", "name"} <= set(lk.columns):
            df["district"] = code.map(lk.drop_duplicates("code").set_index("code")["name"]).fillna(code)
    return df


def ksi_table(data: pd.DataFrame, col, min_n: int = 100) -> pd.DataFrame:
    g = (data.groupby(col, observed=True)
             .agg(collisions=("is_ksi", "size"), ksi=("is_ksi", "sum")).reset_index())
    g["ksi_pct"] = (g["ksi"] / g["collisions"] * 100).round(1)
    return g[g["collisions"] >= min_n]


def top_value(s: pd.Series) -> str:
    s = s.dropna()
    return str(s.mode().iloc[0]) if len(s) else "n/a"


def priority_table(data: pd.DataFrame, min_n: int) -> pd.DataFrame:
    g = (data.groupby("district")
             .agg(collisions=("is_ksi", "size"), ksi=("is_ksi", "sum"),
                  fatal=("severity", lambda s: int((s == "Fatal").sum())),
                  rural_pct=("area", lambda s: round((s == "Rural").mean() * 100)))
             .reset_index())
    g["ksi_pct"] = (g["ksi"] / g["collisions"] * 100).round(1)
    g = g[g["collisions"] >= min_n].copy()
    k = data[data["is_ksi"]]
    for col, name in [("speed_label", "common_speed_limit_in_ksi"),
                      ("road", "common_road_type_in_ksi"), ("light", "common_light_in_ksi")]:
        g[name] = g["district"].map(k.groupby("district")[col].agg(top_value))
    g["priority_score"] = ((g["ksi"].rank(pct=True) * 0.5 + g["ksi_pct"].rank(pct=True) * 0.5) * 100).round(1)
    return g.sort_values("priority_score", ascending=False).reset_index(drop=True)


# ------------------------------ Chart helpers ------------------------------
def bar_ksi(data, col, min_n, horizontal=True, order=None, h=340) -> None:
    """Bars of % fatal/serious per category, heat-coloured, with the overall average marked."""
    t = ksi_table(data, col, min_n)
    if t.empty:
        st.caption("Not enough collisions in this view. Lower the minimum in the sidebar.")
        return
    t[col] = t[col].astype(str)
    t = (t.set_index(col).reindex([o for o in order if o in set(t[col])]).reset_index()
         if order else t.sort_values("ksi_pct"))
    avg = data["is_ksi"].mean() * 100
    mx = max(t["ksi_pct"].max(), 1)
    common = dict(marker=dict(color=t["ksi_pct"], colorscale=HEAT, cmin=0, cmax=mx),
                  text=[f"{v:.1f}%" for v in t["ksi_pct"]], textposition="outside",
                  customdata=t[["collisions", "ksi"]],
                  hovertemplate="<b>%{" + ("y" if horizontal else "x") + "}</b><br>"
                                "%{customdata[1]:,} fatal or serious of %{customdata[0]:,}<extra></extra>")
    if horizontal:
        fig = go.Figure(go.Bar(x=t["ksi_pct"], y=t[col], orientation="h", **common))
        fig.add_vline(x=avg, line_dash="dash", line_color=YELLOW,
                      annotation_text=f"Average {avg:.1f}%", annotation_font_color=YELLOW)
        fig.update_xaxes(range=[0, mx * 1.2], title="% fatal or serious")
    else:
        fig = go.Figure(go.Bar(x=t[col], y=t["ksi_pct"], **common))
        fig.add_hline(y=avg, line_dash="dash", line_color=YELLOW,
                      annotation_text=f"Average {avg:.1f}%", annotation_font_color=YELLOW,
                      annotation_position="top left")
        fig.update_yaxes(range=[0, mx * 1.2], title="% fatal or serious")
    show(style(fig, h))


# ===================================================================
#                               APP
# ===================================================================
inject_css()

try:  # warn if the dark theme file is missing
    if st.context.theme.type == "light":
        st.warning("For the intended look, add the .streamlit/config.toml theme file "
                   "(see config.toml) and restart the app.")
except Exception:
    pass

if not os.path.exists(DATA_FILE):
    st.error(f"'{DATA_FILE}' not found. Put the merged CSV in the same folder as this script.")
    st.stop()

df = load_data()

st.markdown(f"""<div class='hero'><h1>Where Britain's worst road collisions happen</h1>
<p>Built for council transport planners. {len(df):,} police-reported injury collisions
from 2025, broken down by place, road, speed limit, light and time, so budget and speed-limit
reviews can go where they save the most lives.</p></div><div class='centreline'></div>""",
            unsafe_allow_html=True)

# ------------------------------ Sidebar ------------------------------
st.sidebar.markdown("### Narrow the view")
dmin, dmax = df["date"].min().date(), df["date"].max().date()
date_range = st.sidebar.date_input("Dates", (dmin, dmax), dmin, dmax)
area_sel = st.sidebar.multiselect("Area type", sorted(df["area"].unique()), default=sorted(df["area"].unique()))
road_sel = st.sidebar.multiselect("Road type", sorted(df["road"].unique()), default=sorted(df["road"].unique()))
light_sel = st.sidebar.multiselect("Light conditions", sorted(df["light"].unique()), default=sorted(df["light"].unique()))
min_n = st.sidebar.slider("Smallest group to rank", 20, 500, 100, 10,
                          help="Groups with fewer collisions are hidden because their percentages swing too much.")
st.sidebar.caption("KSI means killed or seriously injured: fatal plus serious collisions.")

f = df[df["area"].isin(area_sel) & df["road"].isin(road_sel) & df["light"].isin(light_sel)]
if isinstance(date_range, tuple) and len(date_range) == 2:
    f = f[(f["date"].dt.date >= date_range[0]) & (f["date"].dt.date <= date_range[1])]
if f.empty:
    st.warning("No collisions match these filters. Widen the dates or select more road or area types.")
    st.stop()

avg_ksi = f["is_ksi"].mean() * 100
kpi_strip([
    ("Collisions", len(f), 0, "police-reported injury collisions", URBAN),
    ("Fatal", int((f["severity"] == "Fatal").sum()), 0, "collisions with a death", SEV["Fatal"]),
    ("Serious", int((f["severity"] == "Serious").sum()), 0, "collisions with a serious injury", SEV["Serious"]),
    ("KSI share", round(avg_ksi, 1), 1, "% fatal or serious", YELLOW),
    ("Casualties", int(f["number_of_casualties"].sum()), 0, "people injured or killed", "#fff"),
])

tabs = st.tabs(["Overview", "Where", "Speed and roads", "Conditions", "When", "Who", "Priorities"])

# ------------------------------ Overview ------------------------------
with tabs[0]:
    section("How serious are the collisions?",
            f"About 1 in {max(round(100 / avg_ksi), 1)} collisions leaves someone killed or seriously injured.")
    c1, c2 = st.columns([1, 1.6])
    sev = f["severity"].value_counts().reindex(["Fatal", "Serious", "Slight"]).fillna(0).reset_index()
    sev.columns = ["severity", "n"]
    fig = go.Figure(go.Pie(labels=sev["severity"], values=sev["n"], hole=0.62, sort=False,
                           marker=dict(colors=[SEV[s] for s in sev["severity"]], line=dict(color=BG, width=3)),
                           textinfo="percent", hovertemplate="%{label}: %{value:,}<extra></extra>"))
    fig.add_annotation(text=f"<b>{len(f):,}</b><br>collisions", showarrow=False,
                       font=dict(family=HEAD, size=18, color=INK))
    c1.plotly_chart(style(fig, 380, legend=True), width="stretch", config=CFG)
    m = (f.groupby("month_name").agg(n=("is_ksi", "size"), k=("is_ksi", "mean")).reindex(MONTHS).dropna().reset_index())
    m["k"] *= 100
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=m["month_name"], y=m["n"], name="Collisions", marker_color="#2E6FB7",
                hovertemplate="%{y:,} collisions<extra></extra>", secondary_y=False)
    fig.add_scatter(x=m["month_name"], y=m["k"], name="% fatal or serious", mode="lines+markers",
                    line=dict(color=YELLOW, width=3), marker=dict(size=9, line=dict(color=BG, width=2)),
                    hovertemplate="%{y:.1f}% fatal or serious<extra></extra>", secondary_y=True)
    fig.update_yaxes(title="Collisions", secondary_y=False)
    fig.update_yaxes(title="% fatal or serious", secondary_y=True, showgrid=False, rangemode="tozero")
    c2.plotly_chart(style(fig, 380, legend=True), width="stretch", config=CFG)

# -------------------------------- Where --------------------------------
with tabs[1]:
    section("Where do the worst collisions cluster?",
            "Each column or glow marks a fatal or serious collision. Tall, bright areas are hotspots.")
    geo = f[f["is_ksi"]].dropna(subset=["latitude", "longitude"])
    mode = st.radio("Map view", ["3D hotspots", "Play through the year"], horizontal=True, label_visibility="collapsed")
    if geo.empty:
        st.caption("No fatal or serious collisions with coordinates in this view.")
    elif mode == "3D hotspots" and pdk is not None:
        layer = pdk.Layer(
            "HexagonLayer", data=geo[["longitude", "latitude"]].reset_index(drop=True),
            get_position=["longitude", "latitude"], radius=4000, elevation_scale=60, elevation_range=[0, 3000],
            extruded=True, coverage=0.9, pickable=True, auto_highlight=True,
            color_range=[[18, 50, 90], [46, 111, 183], [120, 170, 200], [247, 198, 0], [242, 140, 30], [229, 56, 59]])
        view = pdk.ViewState(latitude=53.4, longitude=-2.2, zoom=5.1, pitch=52, bearing=-8)
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view,
                                 tooltip={"text": "{elevationValue} fatal or serious collisions in this cell"}),
                        height=560)
    else:
        samp = geo.sample(min(len(geo), 9000), random_state=1)
        order = [mo for mo in MONTHS if mo in set(samp["month_name"])]
        fig = px.density_map(samp, lat="latitude", lon="longitude", animation_frame="month_name",
                             category_orders={"month_name": order}, radius=9, zoom=4.7,
                             center=dict(lat=53.6, lon=-2.5), map_style="carto-darkmatter",
                             color_continuous_scale=HEAT)
        fig.update_layout(coloraxis_showscale=False)
        show(style_anim(style(fig, 560)))
        st.caption("Press play to watch fatal and serious collisions month by month.")

    d = ksi_table(f, "district", min_n)
    if d.empty:
        st.caption("No areas have enough collisions in this view. Lower the minimum in the sidebar.")
    else:
        section("Which council areas have the biggest problem?",
                "Size of the problem (count) and danger of the roads (share) tell different stories.")
        c1, c2 = st.columns(2)
        top = d.sort_values("ksi", ascending=False).head(15)
        fig = go.Figure()
        fig.add_bar(x=top["ksi"], y=top["district"], orientation="h", width=0.1,
                    marker_color="rgba(244,246,248,.45)", hoverinfo="skip", showlegend=False)
        fig.add_scatter(x=top["ksi"], y=top["district"], mode="markers", showlegend=False,
                        marker=dict(size=17, color=top["ksi_pct"], colorscale=HEAT, showscale=True,
                                    colorbar=dict(title="% KSI", thickness=10, len=0.8),
                                    line=dict(color="#fff", width=1.5)),
                        customdata=top[["ksi_pct", "collisions"]],
                        hovertemplate="<b>%{y}</b><br>%{x:,} fatal or serious<br>%{customdata[0]}% of "
                                      "%{customdata[1]:,} collisions<extra></extra>")
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(title="Fatal or serious collisions")
        c1.markdown("**Top 15 by number of fatal or serious collisions**")
        c1.plotly_chart(style(fig, 470), width="stretch", config=CFG)
        mx_c, md_k = d["collisions"].median(), d["ksi_pct"].median()
        fig = go.Figure(go.Scatter(
            x=d["collisions"], y=d["ksi_pct"], mode="markers", customdata=d[["district", "ksi"]],
            marker=dict(size=np.clip(d["ksi"] / d["ksi"].max() * 38, 7, 38), color=d["ksi_pct"], colorscale=HEAT,
                        opacity=0.9, line=dict(color="#fff", width=1)),
            hovertemplate="<b>%{customdata[0]}</b><br>%{x:,} collisions<br>%{y}% fatal or serious<br>"
                          "%{customdata[1]:,} KSI<extra></extra>"))
        fig.add_vline(x=mx_c, line_dash="dash", line_color=MUTED)
        fig.add_hline(y=md_k, line_dash="dash", line_color=MUTED)
        fig.add_annotation(xref="paper", yref="paper", x=0.99, y=0.99, showarrow=False, xanchor="right",
                           text="<b>High volume, high danger</b>", font=dict(color=YELLOW, size=13))
        fig.update_xaxes(title="Total collisions"); fig.update_yaxes(title="% fatal or serious")
        c2.markdown("**Volume against danger** (bubble size = KSI count)")
        c2.plotly_chart(style(fig, 470), width="stretch", config=CFG)

        section("How did the top areas build up over the year?", "Press play to watch the running total of fatal or serious collisions.")
        top10 = d.sort_values("ksi", ascending=False).head(10)["district"].tolist()
        mm = (f[f["is_ksi"] & f["district"].isin(top10)].groupby(["district", "month_name"]).size()
              .unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0).reindex(top10, fill_value=0))
        race = mm.cumsum(axis=1).stack().reset_index()
        race.columns = ["district", "month_name", "cumulative"]
        fig = px.bar(race, x="cumulative", y="district", orientation="h", animation_frame="month_name",
                     category_orders={"district": top10[::-1], "month_name": MONTHS},
                     range_x=[0, max(race["cumulative"].max() * 1.1, 1)], color="cumulative",
                     color_continuous_scale=HEAT)
        fig.update_layout(coloraxis_showscale=False)
        fig.update_xaxes(title="Running total of fatal or serious collisions"); fig.update_yaxes(title="")
        show(style_anim(style(fig, 440)))

# ---------------------------- Speed and roads ----------------------------
with tabs[2]:
    section("Does speed limit relate to severity?",
            "Compare limits inside the same road type. Faster limits sit on faster rural roads, "
            "so the raw comparison alone can mislead.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**% fatal or serious by speed limit**")
        bar_ksi(f.dropna(subset=["speed_label"]), "speed_label", min_n, horizontal=False,
                order=[f"{s} mph" for s in VALID_SPEEDS])
    with c2:
        st.markdown("**Fatal or serious collisions by road type**")
        bar_ksi(f, "road", min_n)

    both = f[f["road"].isin(list(ROAD_TYPE.values()))].dropna(subset=["speed_label"])
    cell = both.groupby(["road", "speed_label"]).agg(collisions=("is_ksi", "size"), ksi=("is_ksi", "sum")).reset_index()
    if not cell.empty:
        cell["ksi_pct"] = (cell["ksi"] / cell["collisions"] * 100).round(1)
        c3, c4 = st.columns(2)
        big = cell[cell["collisions"] >= min_n]
        if not big.empty:
            pv = big.pivot(index="road", columns="speed_label", values="ksi_pct")
            pv = pv.reindex(columns=[f"{s} mph" for s in VALID_SPEEDS if f"{s} mph" in pv.columns])
            fig = px.imshow(pv, text_auto=".1f", aspect="auto", color_continuous_scale=HEAT, zmin=0,
                            labels=dict(color="% KSI", x="", y=""))
            fig.update_traces(xgap=3, ygap=3)
            c3.markdown("**% fatal or serious: road type by speed limit**")
            c3.plotly_chart(style(fig, 400), width="stretch", config=CFG)
        tm = f[(f["area"] != "Unknown") & (f["road"] != "Unknown")].dropna(subset=["speed_label"])
        tm = (tm.groupby(["area", "road", "speed_label"]).agg(collisions=("is_ksi", "size"), ksi=("is_ksi", "sum"))
                .reset_index())
        tm = tm[tm["ksi"] > 0]
        if not tm.empty:
            tm["ksi_pct"] = (tm["ksi"] / tm["collisions"] * 100).round(1)
            fig = px.treemap(tm, path=["area", "road", "speed_label"], values="ksi", color="ksi_pct",
                             color_continuous_scale=HEAT, range_color=[0, max(tm["ksi_pct"].max(), 1)])
            fig.update_traces(marker=dict(line=dict(color=BG, width=2)), textfont=dict(family=BODY, size=14),
                              hovertemplate="<b>%{label}</b><br>%{value:,} fatal or serious<extra></extra>")
            fig.update_layout(coloraxis_colorbar=dict(title="% KSI", thickness=10))
            c4.markdown("**Where the fatal and serious collisions sit** (tile size = KSI count, colour = share)")
            c4.plotly_chart(style(fig, 400), width="stretch", config=CFG)

# ------------------------------ Conditions ------------------------------
with tabs[3]:
    section("Do light, weather and road surface raise the risk?",
            "Councils can change lighting and maintenance. They cannot change the weather, but can plan around it.")
    g = f[f["area"].isin(["Urban", "Rural"])].groupby(["light", "area"]).agg(c=("is_ksi", "size"), k=("is_ksi", "mean")).reset_index()
    g = g[g["c"] >= min_n]
    g["pct"] = g["k"] * 100
    pv = g.pivot(index="light", columns="area", values="pct").dropna() if not g.empty else pd.DataFrame()
    c1, c2 = st.columns(2)
    if {"Urban", "Rural"} <= set(pv.columns) and not pv.empty:
        pv = pv.sort_values("Rural")
        fig = go.Figure()
        for cat, row in pv.iterrows():
            fig.add_scatter(x=[row["Urban"], row["Rural"]], y=[cat, cat], mode="lines", showlegend=False,
                            line=dict(color="rgba(244,246,248,.45)", width=4), hoverinfo="skip")
        for name, colr in [("Urban", URBAN), ("Rural", YELLOW)]:
            fig.add_scatter(x=pv[name], y=pv.index, mode="markers", name=name,
                            marker=dict(size=17, color=colr, line=dict(color="#fff", width=1.5)),
                            hovertemplate="%{y}<br>" + name + ": %{x:.1f}% fatal or serious<extra></extra>")
        fig.update_xaxes(title="% fatal or serious", rangemode="tozero")
        c1.markdown("**Light conditions: urban against rural**")
        c1.plotly_chart(style(fig, 380, legend=True), width="stretch", config=CFG)
    else:
        c1.caption("Not enough urban and rural collisions to compare in this view.")
    with c2:
        st.markdown("**Weather**")
        bar_ksi(f, "weather", min_n, h=380)

    d2 = f[f["area"].isin(["Urban", "Rural"])].copy()
    d2["lg"] = d2["light"].map(LIGHT_GROUP)
    d2 = d2.dropna(subset=["lg"])
    c3, c4 = st.columns(2)
    if not d2.empty:
        nodes = [n for n in ["Urban", "Rural", "Daylight", "Dark, street lit", "Dark, unlit or unknown",
                             "Fatal", "Serious", "Slight"] if n in set(d2["area"]) | set(d2["lg"]) | set(d2["severity"])]
        ix = {n: i for i, n in enumerate(nodes)}
        l1 = d2.groupby(["area", "lg"]).size().reset_index(name="v")
        l2 = d2.groupby(["lg", "severity"]).size().reset_index(name="v")
        colours = {"Urban": URBAN, "Rural": YELLOW, "Daylight": "#CFE0F7", "Dark, street lit": "#7B8FB0",
                   "Dark, unlit or unknown": "#46557A", **SEV}
        fig = go.Figure(go.Sankey(
            node=dict(label=nodes, pad=18, thickness=16, color=[colours[n] for n in nodes],
                      line=dict(color=BG, width=1)),
            link=dict(source=[ix[a] for a in l1["area"]] + [ix[a] for a in l2["lg"]],
                      target=[ix[a] for a in l1["lg"]] + [ix[a] for a in l2["severity"]],
                      value=list(l1["v"]) + list(l2["v"]),
                      color=[hex_rgba(colours[a], .35) for a in l1["area"]] +
                            [hex_rgba(colours[a], .45) for a in l2["severity"]])))
        fig.update_traces(textfont=dict(color=INK, size=13))
        c3.markdown("**How collisions flow: area, light, severity**")
        c3.plotly_chart(style(fig, 400), width="stretch", config=CFG)
    with c4:
        st.markdown("**Road surface**")
        bar_ksi(f, "surface", min_n, h=400)

# --------------------------------- When ---------------------------------
with tabs[4]:
    section("When do collisions happen, and when are they worst?",
            "The busiest hours are not always the most dangerous. Colour shows the share that are fatal or serious.")
    hr = f.groupby("hour").agg(collisions=("is_ksi", "size"), ksi_pct=("is_ksi", "mean")).reindex(range(24)).fillna(0).reset_index()
    hr["ksi_pct"] = (hr["ksi_pct"] * 100).round(1)
    c1, c2 = st.columns([1, 1.2])
    fig = go.Figure(go.Barpolar(
        r=hr["collisions"], theta=hr["hour"] * 15 + 7.5, width=[14] * 24, customdata=hr[["hour", "ksi_pct"]],
        marker=dict(color=hr["ksi_pct"], colorscale=HEAT, cmin=0, cmax=max(hr["ksi_pct"].max(), 1), showscale=True,
                    colorbar=dict(title="% KSI", thickness=10, len=0.8), line=dict(color=BG, width=1)),
        hovertemplate="%{customdata[0]}:00<br>%{r:,} collisions<br>%{customdata[1]}% fatal or serious<extra></extra>"))
    fig.update_layout(polar=dict(
        bgcolor="rgba(0,0,0,0)", radialaxis=dict(showticklabels=False, gridcolor=GRID, linecolor=GRID),
        angularaxis=dict(direction="clockwise", rotation=90, tickmode="array",
                         tickvals=[h * 15 for h in range(0, 24, 3)], ticktext=[f"{h:02d}:00" for h in range(0, 24, 3)],
                         gridcolor=GRID, linecolor=GRID)))
    c1.markdown("**A day on the clock** (bar length = collisions)")
    c1.plotly_chart(style(fig, 440), width="stretch", config=CFG)
    wh = f.groupby(["weekday", "hour"]).agg(collisions=("is_ksi", "size"), ksi_pct=("is_ksi", "mean")).reset_index()
    wh["ksi_pct"] = (wh["ksi_pct"] * 100).round(1)
    fig = px.bar(wh, x="hour", y="collisions", color="ksi_pct", animation_frame="weekday",
                 category_orders={"weekday": [d for d in WEEK_ORDER if d in set(wh["weekday"])]},
                 range_y=[0, max(wh["collisions"].max() * 1.1, 1)], range_color=[0, max(wh["ksi_pct"].max(), 1)],
                 color_continuous_scale=HEAT, labels={"ksi_pct": "% KSI", "hour": "Hour of day", "collisions": "Collisions"})
    fig.update_layout(coloraxis_colorbar=dict(thickness=10))
    c2.markdown("**Press play to step through the week**")
    c2.plotly_chart(style_anim(style(fig, 440)), width="stretch", config=CFG)

    heat = (f[f["is_ksi"]].groupby(["weekday", "hour"]).size().unstack(fill_value=0)
            .reindex(index=WEEK_ORDER, columns=range(24), fill_value=0))
    fig = px.imshow(heat, aspect="auto", color_continuous_scale=HEAT, labels=dict(x="Hour", y="", color="KSI"))
    fig.update_traces(xgap=2, ygap=2)
    st.markdown("**Fatal and serious collisions: weekday by hour**")
    show(style(fig, 330))

# ---------------------------------- Who ----------------------------------
with tabs[5]:
    section("Who is most at risk?",
            "Vehicle columns describe the first vehicle in each collision and casualty columns the most severe "
            "casualty. Read charts as 'in X% of collisions', not 'X% of all vehicles or casualties'.")
    c1, c2 = st.columns(2)
    cc = (f[f["casualty_class_label"] != "Unknown"].groupby(["casualty_class_label", "severity"]).size()
          .reset_index(name="n"))
    if not cc.empty:
        fig = px.sunburst(cc, path=["casualty_class_label", "severity"], values="n", color="severity",
                          color_discrete_map={**SEV, "(?)": SIGN})
        fig.update_traces(marker=dict(line=dict(color=BG, width=2)), textfont=dict(family=BODY, size=14),
                          hovertemplate="<b>%{label}</b><br>%{value:,} collisions<extra></extra>")
        c1.markdown("**Most severely hurt person: road-user type and severity**")
        c1.plotly_chart(style(fig, 400), width="stretch", config=CFG)
    with c2:
        st.markdown("**% fatal or serious by casualty age group**")
        bar_ksi(f.dropna(subset=["casualty_age_group"]), "casualty_age_group", min_n, horizontal=False,
                order=["0-15", "16-24", "25-39", "40-59", "60+"], h=400)
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**% fatal or serious by first vehicle type**")
        bar_ksi(f, "vehicle_group", min_n, h=340)
    with c4:
        st.markdown("**% fatal or serious by first driver age group**")
        bar_ksi(f.dropna(subset=["driver_age_group"]), "driver_age_group", min_n, horizontal=False,
                order=["Under 25", "25-39", "40-59", "60+"], h=340)

# ------------------------------- Priorities -------------------------------
with tabs[6]:
    pt = priority_table(f, min_n)
    section("Where should the budget go first?",
            "Ranked on two things equally: how many fatal or serious collisions an area has, and how large a "
            "share of its collisions they are. A starting point for discussion, not a final decision.")
    if pt.empty:
        st.caption("No areas have enough collisions in this view. Lower the minimum in the sidebar.")
    else:
        posts = ""
        for i, r in pt.head(5).iterrows():
            posts += (f"<div class='post'><div class='rank'>{i + 1}</div>"
                      f"<div class='pname'>{html.escape(str(r['district']))}</div>"
                      f"<div class='pstat'><b>{int(r['ksi']):,}</b> fatal or serious collisions</div>"
                      f"<div class='pstat'><b>{r['ksi_pct']:.1f}%</b> of all its collisions</div>"
                      f"<div class='pwhy'>Most common in its severe collisions: {html.escape(r['common_road_type_in_ksi'])}, "
                      f"{html.escape(r['common_speed_limit_in_ksi'])}, {html.escape(r['common_light_in_ksi'].lower())}.</div></div>")
        st.markdown(posts, unsafe_allow_html=True)
        st.dataframe(
            pt.rename(columns={"district": "Council area"}), width="stretch", height=380, hide_index=True,
            column_config={
                "collisions": st.column_config.NumberColumn("Collisions", format="%d"),
                "ksi": st.column_config.NumberColumn("Fatal or serious", format="%d"),
                "fatal": st.column_config.NumberColumn("Fatal", format="%d"),
                "ksi_pct": st.column_config.ProgressColumn("% fatal or serious", format="%.1f%%", min_value=0,
                                                           max_value=float(max(pt["ksi_pct"].max(), 1))),
                "rural_pct": st.column_config.ProgressColumn("% rural", format="%d%%", min_value=0, max_value=100),
                "priority_score": st.column_config.ProgressColumn("Priority score", format="%.0f", min_value=0, max_value=100),
                "common_speed_limit_in_ksi": "Common speed limit",
                "common_road_type_in_ksi": "Common road type",
                "common_light_in_ksi": "Common light"})
        st.download_button("Download priority table (CSV)", pt.to_csv(index=False).encode("utf-8"),
                           "priority_table.csv", "text/csv")

    # ---- Data-driven findings and recommendations ----
    findings, recs = [], []
    if not pt.empty:
        top3 = ", ".join(pt["district"].head(3))
        recs.append(f"**Start with {top3}.** They score highest on both the number and the share of fatal or serious collisions.")
    sp = ksi_table(f.dropna(subset=["speed_label"]), "speed_label", min_n)
    both = f[f["road"].isin(list(ROAD_TYPE.values()))].dropna(subset=["speed_label"])
    cl = both.groupby(["road", "speed_label"]).agg(c=("is_ksi", "size"), p=("is_ksi", "mean")).reset_index()
    cl = cl[cl["c"] >= max(min_n, 200)]
    if not cl.empty:
        r = cl.sort_values("p", ascending=False).iloc[0]
        findings.append(f"**Speed and road type:** {r['road'].lower()}s with a {r['speed_label']} limit have the highest "
                        f"fatal or serious share, {r['p'] * 100:.1f}% against {avg_ksi:.1f}% overall.")
        recs.append(f"**Review the {r['speed_label']} limit on {r['road'].lower()}s** and the junctions and crossings along them.")
    dark, day = f[f["light"].isin(DARK)], f[f["light"] == "Daylight"]
    if len(dark) >= min_n and len(day) >= min_n and day["is_ksi"].mean() > 0:
        ratio = dark["is_ksi"].mean() / day["is_ksi"].mean()
        findings.append(f"**Lighting:** {dark['is_ksi'].mean() * 100:.1f}% of collisions in the dark are fatal or serious, "
                        f"against {day['is_ksi'].mean() * 100:.1f}% in daylight ({ratio:.1f} times as likely).")
        if ratio > 1:
            recs.append("**Check street lighting** on roads where dark-condition collisions cluster, starting with the top-ranked areas.")
    ur = ksi_table(f[f["area"] != "Unknown"], "area", min_n)
    if len(ur) == 2:
        a = ur.set_index("area")["ksi_pct"]
        findings.append(f"**Urban and rural:** {a['Rural']}% of rural collisions are fatal or serious against {a['Urban']}% in urban areas.")
    hh = f.groupby("hour").agg(c=("is_ksi", "size"), k=("is_ksi", "mean"))
    hh = hh[hh["c"] >= 50]
    if not hh.empty:
        findings.append(f"**Timing:** collisions peak at {f.groupby('hour').size().idxmax():02d}:00, but the highest "
                        f"fatal or serious share is at {hh['k'].idxmax():02d}:00.")
        recs.append(f"**Time enforcement and campaigns** around {hh['k'].idxmax():02d}:00 as well as the busy peaks.")
    k = f[f["is_ksi"]]
    if len(k) >= 50:
        ped = (k["casualty_class_label"] == "Pedestrian").mean() * 100
        findings.append(f"**Vulnerable road users:** in {ped:.0f}% of fatal or serious collisions the most severely hurt person was a pedestrian.")
        recs.append("**Protect pedestrians and other vulnerable users** with crossings and junction changes where they appear most.")

    c1, c2 = st.columns(2)
    with c1:
        section("What the data shows", "Updates with the filters in the sidebar.")
        for line in findings:
            st.markdown("- " + line)
    with c2:
        section("What to do about it")
        for i, line in enumerate(recs, 1):
            st.markdown(f"{i}. {line}")
    st.warning("These are associations, not causes. The open data has no traffic volumes or contributory factors "
               "such as speeding. It covers police-reported injury collisions for one year only.")