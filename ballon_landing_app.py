import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import requests
from datetime import datetime
import matplotlib.pyplot as plt


def wind_to_components(speed, direction_deg):
    direction_rad = np.deg2rad(direction_deg)
    u = -speed * np.sin(direction_rad)
    v = -speed * np.cos(direction_rad)
    return u, v



        except:
            st.stop()

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        alt = st.number_input("Abstiegshöhe (AMSL)", min_value=500, max_value=30000, value=6000, step=100)
    with col2:
        sink_rate = st.number_input("Durchschnittliche Sinkrate (m/s)", min_value=1.5, max_value=6.0, value=4.5, step=0.1)
    with col3:
        reduce_ab_hoehe = st.number_input("Sinkrate ab Höhe reduzieren (m)", min_value=0, max_value=1000, value=300, step=50)
    st.markdown("### Modus- und Datenquellenwahl")
    col_modus, col_daten = st.columns([1, 1])
    with col_modus:
        mode = st.radio("Simulationsmodus", ["Vorwärts: Abstiegspunkt → Landepunkt", "Rückwärts: Zielort → Startpunkt"])
    with col_daten:
        model_source = st.radio("Datenquelle", ["Radiosonde (gemessen, wenn verfügbar)", "GFS (Modell, fallback)"])
    st.session_state["fallback_to_gfs"] = (model_source == "GFS (Modell, fallback)")
    st.session_state["fallback_to_gfs"] = (model_source == "GFS (Modell, fallback)")
    submitted = st.button("Simulation starten")

    

     + (alt - 100) / (reduce_below - 100) * (base_rate - min_rate)
    else:
        return min_rate

def simulate_descent(lat, lon, alt, sink_rate, wind_speeds, wind_dirs, altitudes, reduce_ab_hoehe):
    path = [(lat, lon)]
    dt = 1
    time = 0
    current_alt = alt

    while current_alt > 0:
        local_sink = interpolate_sinkrate(current_alt, sink_rate, 0.5, reduce_ab_hoehe)
        current_alt -= local_sink * dt
        wind_speed = np.interp(current_alt, altitudes, wind_speeds)
        wind_dir = np.interp(current_alt, altitudes, wind_dirs)
        u, v = wind_to_components(wind_speed, wind_dir)

        dlat = (v * dt) / 111320
        dlon = (u * dt) / (40075000 * np.cos(np.radians(lat)) / 360)

        lat += dlat
        lon += dlon
        path.append((lat, lon))
        time += dt

    return path, time

def reverse_projection(lat, lon, alt, sink_rate, wind_speeds, wind_dirs, altitudes, reduce_ab_hoehe):
    path = [(lat, lon)]
    dt = 1
    time = 0
    current_alt = alt

    while current_alt > 0:
        local_sink = interpolate_sinkrate(current_alt, sink_rate, 0.5, reduce_ab_hoehe)
        current_alt -= local_sink * dt
        wind_speed = np.interp(current_alt, altitudes, wind_speeds)
        wind_dir = np.interp(current_alt, altitudes, wind_dirs)
        u, v = wind_to_components(wind_speed, wind_dir)

        dlat = (v * dt) / 111320
        dlon = (u * dt) / (40075000 * np.cos(np.radians(lat)) / 360)

        lat -= dlat
        lon -= dlon
        path.append((lat, lon))
        time += dt

    return path[::-1], time


if submitted:
        # Marker für aktuelle Position setzen
        if lat and lon:
            st.session_state.last_clicked_coords = (lat, lon)

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
                    path, total_time = simulate_descent(lat, lon, alt, sink_rate, wind_speeds, wind_dirs, altitudes, reduce_ab_hoehe)
                else:
                    path, total_time = reverse_projection(lat, lon, alt, sink_rate, wind_speeds, wind_dirs, altitudes, reduce_ab_hoehe)

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

        st_folium(fmap_result, height=500, use_container_width=True)



