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
    fallback = st.session_state.get("fallback_to_gfs", False)
    try:
        return fetch_radiosonde_profile(lat, lon)
    except Exception as e:
        if fallback:
            st.warning("Radiosondenprofil nicht verfügbar. GFS-Daten werden verwendet.")
            return fetch_gfs_model(lat, lon)
        else:
            raise e

import socket

def fetch_radiosonde_profile(lat, lon):
        # 1. Finde nächste Station
        # Prüfen, ob Domain aufgelöst werden kann
    try:
        socket.gethostbyname("api.skewt.org")
    except socket.gaierror:
        raise ConnectionError("Die Adresse 'api.skewt.org' konnte nicht aufgelöst werden. Bitte GFS-Fallback aktivieren.")

    nearest_url = f"https://api.skewt.org/nearest?lat={lat}&lon={lon}"
    nearest_response = requests.get(nearest_url, timeout=5)
    nearest_data = nearest_response.json()
    st.write("**Nächstgelegene Radiosondenstation:**", nearest_data["station"], f"(WMO-ID: {nearest_data['wmo_id']})")

    # 2. Lade Profil
    profile_url = f"https://api.skewt.org/?wmo_id={nearest_data['wmo_id']}"
        profile_response = requests.get(profile_url, timeout=5)
    profile_data = profile_response.json()

    altitudes = []
    wind_speeds = []
    wind_dirs = []

    for level in profile_data["profile"]:
        if all(k in level for k in ["z", "wind_speed", "wind_dir"]):
            altitudes.append(level["z"])
            wind_speeds.append(level["wind_speed"])
            wind_dirs.append(level["wind_dir"])

    model_time = profile_data["time"]
    return np.array(wind_speeds), np.array(wind_dirs), np.array(altitudes), model_time


import matplotlib.pyplot as plt

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

    input_mode = st.radio("Positions-Eingabe", ["Interaktive Karte", "Koordinateneingabe"])

    if input_mode == "Interaktive Karte":
        st.subheader("Punkt auf Karte wählen")
        map_center = [47.37, 8.55]
        fmap = folium.Map(location=map_center, zoom_start=6)
        fmap.add_child(folium.LatLngPopup())
        map_result = st_folium(fmap, height=500, width=1000, returned_objects=["last_clicked"], use_container_width=True)

        if map_result and map_result.get("last_clicked"):
            lat = map_result["last_clicked"]["lat"]
            lon = map_result["last_clicked"]["lng"]
        else:
            lat, lon = None, None

    if input_mode == "Koordinateneingabe" or (input_mode == "Interaktive Karte" and lat is None):
        st.subheader("Koordinaten manuell eingeben")
        col1, col2 = st.columns(2)
        with col1:
            lat = st.number_input("Breitengrad", value=47.37)
        with col2:
            lon = st.number_input("Längengrad", value=8.55)
    else:
        col1, col2 = st.columns(2)
        with col1:
            lat = st.number_input("Breitengrad", value=47.37)
        with col2:
            lon = st.number_input("Längengrad", value=8.55)

    alt = st.number_input("Abstiegshöhe in Metern", min_value=500, max_value=30000, value=6000, step=100)
    sink_rate = st.slider("Maximale Sinkrate (m/s)", min_value=1.5, max_value=6.0, value=4.5, step=0.1)
    model_source = st.radio("Datenquelle", ["Radiosonde (gemessen, wenn verfügbar)", "GFS (Modell, fallback)"])
    st.session_state["fallback_to_gfs"] = (model_source == "GFS (Modell, fallback)")
    submitted = st.button("Simulation starten")

    if submitted:
        with st.spinner("Hole Winddaten und berechne Pfad ..."):
            try:
                wind_speeds, wind_dirs, altitudes, model_time = fetch_gfs_profile(lat, lon)
                st.success(f"Winddaten aus Modelllauf: {model_time}")
                # Visualisierung Vertikalprofil
                st.markdown("### Vertikalprofil (Wind)")
                fig, ax1 = plt.subplots()
                ax1.plot(wind_speeds, altitudes, label="Windgeschwindigkeit [m/s]", color="tab:blue")
                ax1.set_xlabel("Windgeschwindigkeit [m/s]")
                ax1.set_ylabel("Höhe [m]")
                ax1.grid(True)
                st.pyplot(fig)

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

        from folium import Map, FitBounds

        bounds = [[min(p[0] for p in path), min(p[1] for p in path)], [max(p[0] for p in path), max(p[1] for p in path)]]
        fmap_result = Map()
        fmap_result.fit_bounds(bounds)
        folium.Marker(path[0], tooltip="Abstiegspunkt", icon=folium.Icon(color="green")).add_to(fmap_result)
        folium.Marker(path[-1], tooltip="Landepunkt", icon=folium.Icon(color="red")).add_to(fmap_result)
        folium.PolyLine(path, color="blue", weight=2.5, opacity=0.8).add_to(fmap_result)

        st_folium(fmap_result, height=600, width=1000)


if __name__ == "__main__":
    main()
