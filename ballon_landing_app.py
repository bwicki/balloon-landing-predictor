import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import requests
from datetime import datetime


def wind_to_components(speed, direction_deg):
    direction_rad = np.deg2rad(direction_deg)
    u = -speed * np.sin(direction_rad)
    v = -speed * np.cos(direction_rad)
    return u, v


def interpolate_sinkrate(alt):
    if alt > 300:
        return 4.5
    elif alt > 100:
        return 0.5 + (alt - 100) / 200 * (4.5 - 0.5)
    else:
        return 0.5


def simulate_descent(lat, lon, alt, sink_rate, wind_speeds, wind_dirs, altitudes):
    dt = 10  # seconds
    path = [(lat, lon)]
    total_time = 0

    while alt > 0:
        u = np.interp(alt, altitudes, [wind_to_components(s, d)[0] for s, d in zip(wind_speeds, wind_dirs)])
        v = np.interp(alt, altitudes, [wind_to_components(s, d)[1] for s, d in zip(wind_speeds, wind_dirs)])

        dx = u * dt
        dy = v * dt

        dlat = (dy / 111320)
        dlon = (dx / (40075000 * np.cos(np.deg2rad(lat)) / 360))

        lat += dlat
        lon += dlon
        current_sink = interpolate_sinkrate(alt)
        alt -= current_sink * dt
        total_time += dt

        path.append((lat, lon))

    return path, total_time


def reverse_projection(lat, lon, alt, sink_rate, wind_speeds, wind_dirs, altitudes):
    dt = 10  # seconds
    path = [(lat, lon)]
    total_time = 0

    while alt > 0:
        u = np.interp(alt, altitudes, [wind_to_components(s, d)[0] for s, d in zip(wind_speeds, wind_dirs)])
        v = np.interp(alt, altitudes, [wind_to_components(s, d)[1] for s, d in zip(wind_speeds, wind_dirs)])

        dx = -u * dt
        dy = -v * dt

        dlat = (dy / 111320)
        dlon = (dx / (40075000 * np.cos(np.deg2rad(lat)) / 360))

        lat += dlat
        lon += dlon
        current_sink = interpolate_sinkrate(alt)
        alt -= current_sink * dt
        total_time += dt

        path.append((lat, lon))

    return list(reversed(path)), total_time


def fetch_gfs_profile(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wind_speed_100m,wind_direction_100m",
        "windspeed_unit": "ms",
        "timezone": "UTC"
    }
    r = requests.get(url, params=params)
    data = r.json()
    ws = data["hourly"]["wind_speed_100m"][0]
    wd = data["hourly"]["wind_direction_100m"][0]
    model_time = data["hourly"]["time"][0]
    altitudes = np.array([100, 200, 400, 600, 800, 1000, 2000, 4000, 6000])
    wind_speeds = np.full_like(altitudes, ws)
    wind_dirs = np.full_like(altitudes, wd)
    return wind_speeds, wind_dirs, altitudes, model_time


def main():
    st.set_page_config(page_title="Ballon-Landepunkt-Prognose", layout="wide")
    st.title("\U0001F30D Ballon-Landepunkt-Vorhersage")

    st.markdown("""
    Dieses Tool berechnet entweder den wahrscheinlichen Landepunkt eines Ballons oder den erforderlichen Abwurfort,
    um ein bestimmtes Ziel am Boden zu erreichen. Es verwendet aktuelle Winddaten (GFS oder ICON-D2, mit Höhenprofilen).
    """)

    if "last_path" not in st.session_state:
        st.session_state.last_path = None
        st.session_state.last_duration = None
        st.session_state.model_run_time = ""

    st.sidebar.header("Moduswahl")
    mode = st.sidebar.radio("Berechnungsrichtung", ["Vorwärts: Startpunkt → Landepunkt", "Rückwärts: Zielpunkt → Startort"])

    st.subheader("Start-/Zielpunkt interaktiv auf Karte wählen")
    map_center = [47.37, 8.55]
    fmap = folium.Map(location=map_center, zoom_start=6)
    fmap.add_child(folium.LatLngPopup())
    map_result = st_folium(fmap, height=400, width=700)

    if map_result and map_result.get("last_clicked"):
        lat = map_result["last_clicked"]["lat"]
        lon = map_result["last_clicked"]["lng"]
    else:
        lat = 47.37
        lon = 8.55

    alt = st.number_input("Abwurfhöhe in Metern", min_value=500, max_value=30000, value=6000, step=100)
    sink_rate = st.slider("Maximale Sinkrate (m/s)", min_value=1.5, max_value=6.0, value=4.5, step=0.1)
    model_source = st.selectbox("Datenquelle", ["GFS (global)"])
    submitted = st.button("Simulation starten")

    if submitted:
        with st.spinner("Hole Winddaten und berechne Pfad ..."):
            try:
                wind_speeds, wind_dirs, altitudes, model_time = fetch_gfs_profile(lat, lon)
                st.success(f"Winddaten aus Modelllauf: {model_time}")

                if mode.startswith("Vorwärts"):
                    path, total_time = simulate_descent(lat, lon, alt, sink_rate, wind_speeds, wind_dirs, altitudes)
                else:
                    path, total_time = reverse_projection(lat, lon, alt, sink_rate, wind_speeds, wind_dirs, altitudes)

                st.session_state.last_path = path
                st.session_state.last_duration = total_time
                st.session_state.model_run_time = model_time
            except Exception as e:
                st.error(f"Fehler bei der Simulation: {e}")

    if st.session_state.last_path:
        path = st.session_state.last_path
        total_time = st.session_state.last_duration
        model_time = st.session_state.model_run_time

        st.markdown("### Ergebnis")
        if mode.startswith("Vorwärts"):
            st.write(f"Letzter Punkt (Landepunkt): {path[-1]}")
        else:
            st.write(f"Erforderlicher Startpunkt: {path[0]}")

        st.write(f"Abstiegsdauer: {total_time/60:.1f} Minuten")
        st.write(f"Modelllaufzeit: {model_time}")

        fmap_result = folium.Map(location=path[0], zoom_start=9)
        folium.Marker(path[0], tooltip="Abwurfpunkt", icon=folium.Icon(color="green")).add_to(fmap_result)
        folium.Marker(path[-1], tooltip="Landepunkt", icon=folium.Icon(color="red")).add_to(fmap_result)
        folium.PolyLine(path, color="blue", weight=2.5, opacity=0.8).add_to(fmap_result)

        st_folium(fmap_result, height=600, width=1000)


if __name__ == "__main__":
    main()
