import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import requests
from datetime import datetime
import matplotlib.pyplot as plt

# Höhenabfrage (Open-Elevation)
# GFS Windprofil von Open-Meteo API

def fetch_gfs_profile(lat, lon):
    try:
        now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=wind_speed_100m,wind_direction_100m&models=gfs&timezone=UTC"
        response = requests.get(url, timeout=10)
        data = response.json()

        wind_speeds = [ws for ws in data['hourly']['wind_speed_100m'][:20]]
        wind_dirs = [wd for wd in data['hourly']['wind_direction_100m'][:20]]
        altitudes = np.linspace(0, 6000, len(wind_speeds))
        model_time = data['hourly']['time'][0]
        return wind_speeds, wind_dirs, altitudes, model_time
    except Exception as e:
        raise RuntimeError(f"Fehler beim Abrufen der GFS-Winddaten: {e}")
def fetch_terrain_height(lat, lon):
    try:
        url = f"https://api.opentopodata.org/v1/srtm90m?locations={lat},{lon}"
        response = requests.get(url, timeout=5)
        data = response.json()
        return data['results'][0]['elevation']
    except:
        return 0  # Fallback bei Fehler


def interpolate_sinkrate(alt_agl, base_rate=4.5, min_rate=0.5, reduce_below=300):
    if alt_agl > reduce_below:
        return base_rate
    elif alt_agl > 100:
        return min_rate + (alt_agl - 100) / (reduce_below - 100) * (base_rate - min_rate)
    else:
        return min_rate

def wind_to_components(speed, direction_deg):
    direction_rad = np.deg2rad(direction_deg)
    u = -speed * np.sin(direction_rad)
    v = -speed * np.cos(direction_rad)
    return u, v

def simulate_descent(lat, lon, alt, sink_rate, wind_speeds, wind_dirs, altitudes, reduce_ab_hoehe):
    terrain_alt = fetch_terrain_height(lat, lon)
    path = [(lat, lon)]
    dt = 1
    time = 0
    current_alt = alt

    while current_alt > 0:
        alt_agl = current_alt - terrain_alt
        local_sink = interpolate_sinkrate(alt_agl, sink_rate, 0.5, reduce_ab_hoehe)
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
    terrain_alt = fetch_terrain_height(lat, lon)
    path = [(lat, lon)]
    dt = 1
    time = 0
    current_alt = alt

    while current_alt > 0:
        alt_agl = current_alt - terrain_alt
        local_sink = interpolate_sinkrate(alt_agl, sink_rate, 0.5, reduce_ab_hoehe)
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

# Dieser Block muss innerhalb einer App-Funktion stehen, z. B. main()
# Hier als direkter Streamlit-Ausführungsblock

def main():
    st.title("Ballon-Landepunkt-Prognose")

    # Eingabemaske für Startparameter
    col_mode, col_sim = st.columns(2)
    with col_mode:
        input_mode = st.radio("Eingabemodus", ["Manuell (Koordinaten)", "Interaktive Karte"])
    with col_sim:
        mode = st.radio("Simulationsmodus", ["Vorwärts", "Rückwärts"])

    st.markdown(f"### {'Startpunkt' if mode == 'Vorwärts' else 'Landepunkt'}")

    if input_mode == "Interaktive Karte":
        st.markdown("Wähle einen Punkt auf der Karte:")
        default_location = [47.37, 8.55]
        fmap = folium.Map(location=default_location, zoom_start=6)
        fmap.add_child(folium.LatLngPopup())
        map_result = st_folium(fmap, height=500, use_container_width=True)

        if map_result and map_result.get("last_clicked"):
            lat = map_result["last_clicked"]["lat"]
            lon = map_result["last_clicked"]["lng"]
        else:
            lat = 47.37
            lon = 8.55

    if input_mode == "Manuell (Koordinaten)":
        
        col1, col2 = st.columns(2)
        with col1:
            lat_str = st.text_input("Breitengrad (z. B. 47.37N)", value="47.37N")
        with col2:
            lon_str = st.text_input("Längengrad (z. B. 8.55E)", value="8.55E")

        try:
            lat = float(lat_str[:-1]) * (1 if lat_str[-1].upper() == 'N' else -1)
            lon = float(lon_str[:-1]) * (1 if lon_str[-1].upper() == 'E' else -1)
        except:
            st.warning("Bitte gültige Koordinaten eingeben.")
            st.stop()

        st.markdown("---")
        st.markdown("### Koordinaten umrechnen")
        with st.expander("GMS (Grad, Minuten, Sekunden) → Dezimalgrad"):
            col_gms1, col_gms2 = st.columns(2)
            with col_gms1:
                deg_lat = st.number_input("Breitengrad (Grad)", value=47)
                min_lat = st.number_input("Breitengrad (Minuten)", value=22)
                sec_lat = st.number_input("Breitengrad (Sekunden)", value=12.0)
                hemi_lat = st.selectbox("N/S", ["N", "S"])
            with col_gms2:
                deg_lon = st.number_input("Längengrad (Grad)", value=8)
                min_lon = st.number_input("Längengrad (Minuten)", value=33)
                sec_lon = st.number_input("Längengrad (Sekunden)", value=0.0)
                hemi_lon = st.selectbox("E/W", ["E", "W"])

            if st.button("Umrechnen"):
                dec_lat = (deg_lat + min_lat / 60 + sec_lat / 3600) * (1 if hemi_lat == "N" else -1)
                dec_lon = (deg_lon + min_lon / 60 + sec_lon / 3600) * (1 if hemi_lon == "E" else -1)
                st.success(f"Dezimalgrad: {dec_lat:.6f}, {dec_lon:.6f}")

    col3, col4, col5 = st.columns(3)
    with col3:
        alt = st.number_input("Abstiegshöhe (AMSL)", min_value=500, max_value=30000, value=6000, step=100)
    with col4:
        sink_rate = st.number_input("Durchschnittliche Sinkrate (m/s)", min_value=1.5, max_value=6.0, value=4.5, step=0.1)
    with col5:
        reduce_ab_hoehe = st.number_input("Sinkrate reduzieren ab Höhe (m AGL)", min_value=0, max_value=1000, value=300, step=50)

    submitted = st.button("Simulation starten")

    if submitted:
        st.session_state.last_clicked_coords = (lat, lon)

        with st.spinner("Hole Winddaten und berechne Pfad ..."):
            try:
                wind_speeds, wind_dirs, altitudes, model_time = fetch_gfs_profile(lat, lon)

                st.success(f"Winddaten aus Modelllauf: {model_time}")
                st.markdown("### Vertikalprofil (Wind)")
                fig, ax1 = plt.subplots()
                ax1.plot(wind_speeds, altitudes, label="Windgeschwindigkeit [m/s]", color="tab:blue")
                ax1.set_xlabel("Windgeschwindigkeit [m/s]")
                ax1.set_ylabel("Höhe [m]")
                ax1.grid(True)
                st.pyplot(fig, clear_figure=False)

                if mode.startswith("Vorwärts"):
                    path, total_time = simulate_descent(lat, lon, alt, sink_rate, wind_speeds, wind_dirs, altitudes, reduce_ab_hoehe)
                else:
                    path, total_time = reverse_projection(lat, lon, alt, sink_rate, wind_speeds, wind_dirs, altitudes, reduce_ab_hoehe)

                st.session_state.last_path = path
                st.session_state.last_duration = total_time
                st.session_state.model_run_time = model_time
            except Exception as e:
                st.error(f"Fehler bei der Simulation: {e}")

    if st.session_state.get("last_path"):
        path = st.session_state.last_path
        total_time = st.session_state.last_duration
        model_time = st.session_state.model_run_time

        st.markdown("### Ergebnis")
        result_coords = path[-1] if mode.startswith("Vorwärts") else path[0]
        terrain_height = fetch_terrain_height(result_coords[0], result_coords[1])
        st.write(f"Geländehöhe am Zielpunkt: {terrain_height:.0f} m AMSL")
        ns = 'N' if result_coords[0] >= 0 else 'S'
        ew = 'E' if result_coords[1] >= 0 else 'W'
        icao_lat = f"{abs(result_coords[0]):.4f}°{ns}"
        icao_lon = f"{abs(result_coords[1]):.4f}°{ew}"
        if mode.startswith("Vorwärts"):
            st.write(f"Letzter Punkt (Landepunkt): {icao_lat}, {icao_lon}")
        else:
            st.write(f"Erforderlicher Startpunkt: {icao_lat}, {icao_lon}")

        st.write(f"Abstiegsdauer: {total_time/60:.1f} Minuten")
        st.write(f"Modelllaufzeit: {model_time}")

        bounds = [[min(p[0] for p in path), min(p[1] for p in path)], [max(p[0] for p in path), max(p[1] for p in path)]]
        fmap_result = folium.Map()
        fmap_result.fit_bounds(bounds)
        folium.Marker(path[0], tooltip="Abstiegspunkt", icon=folium.Icon(color="green")).add_to(fmap_result)
        folium.Marker(path[-1], tooltip="Landepunkt", icon=folium.Icon(color="red")).add_to(fmap_result)
        folium.PolyLine(path, color="blue", weight=2.5, opacity=0.8).add_to(fmap_result)
        for i in range(1, len(path)):
            folium.RegularPolygonMarker(
                location=path[i],
                number_of_sides=3,
                radius=6,
                rotation=wind_dirs[min(i, len(wind_dirs)-1)],
                color='blue',
                fill=True,
                fill_opacity=0.7
            ).add_to(fmap_result)

        from streamlit.components.v1 import html
        from folium.plugins import TimestampedGeoJson

        animated_features = [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [pt[1], pt[0]]},
            "properties": {"time": f"{i:02d}:00:00", "style": {"color": "red"}, "icon": "circle"}
        } for i, pt in enumerate(path)]

        TimestampedGeoJson({
            "type": "FeatureCollection",
            "features": animated_features
        }, period="PT1M", add_last_point=True, transition_time=200, loop=False, auto_play=True).add_to(fmap_result)

        st_folium(fmap_result, height=500, use_container_width=True)


if __name__ == "__main__":
    main()
