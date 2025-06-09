import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import requests
from datetime import datetime
import math

# Höhenabfrage (Open-Elevation)
# GFS Windprofil von Open-Meteo API

def fetch_gfs_profile(lat, lon):
    try:
        now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=wind_speed_100m,wind_direction_100m,wind_speed_10m,wind_direction_10m&models=gfs&timezone=UTC"
        response = requests.get(url, timeout=10)
        data = response.json()

        if 'hourly' not in data:
            raise RuntimeError("Die GFS-Antwort enthält keine stündlichen Daten.")

        hourly = data['hourly']

        if 'wind_speed_100m' in hourly and 'wind_direction_100m' in hourly:
            wind_speeds = [ws for ws in hourly['wind_speed_100m'][:20]]
            wind_dirs = [wd for wd in hourly['wind_direction_100m'][:20]]
            height_label = "100 m"
        elif 'wind_speed_10m' in hourly and 'wind_direction_10m' in hourly:
            wind_speeds = [ws for ws in hourly['wind_speed_10m'][:20]]
            wind_dirs = [wd for wd in hourly['wind_direction_10m'][:20]]
            height_label = "10 m"
        else:
            available = list(hourly.keys())
            raise RuntimeError(f"Keine nutzbaren Winddaten verfügbar. Verfügbare Felder: {available}")

        altitudes = np.linspace(0, 6000, len(wind_speeds))
        model_time = hourly['time'][0]
        show_wind_profile(wind_speeds, altitudes, model_time)
        return wind_speeds, wind_dirs, altitudes, model_time

        wind_speeds = [ws for ws in data['hourly']['wind_speed_100m'][:20]]
        wind_dirs = [wd for wd in data['hourly']['wind_direction_100m'][:20]]
        altitudes = np.linspace(0, 6000, len(wind_speeds))
        model_time = data['hourly']['time'][0]
        show_wind_profile(wind_speeds, altitudes, model_time)
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

# Hinweis: matplotlib und plotly wurden entfernt, da sie im aktuellen Sandbox-Umfeld nicht verfügbar sind.

def show_wind_profile(wind_speeds, altitudes, model_time):
    st.subheader(f"Vertikales Windprofil (GFS) – Modelllauf: {model_time}")
    profile_data = [
        {"Höhe (m AMSL)": int(alt), "Windgeschwindigkeit (m/s)": round(ws, 1)}
        for alt, ws in zip(altitudes, wind_speeds)
    ]
    st.table(profile_data)

def decimal_to_icao(lat, lon):
    def to_dms(value, is_lat):
        direction = ('N' if value >= 0 else 'S') if is_lat else ('E' if value >= 0 else 'W')
        abs_val = abs(value)
        degrees = int(abs_val)
        minutes_float = (abs_val - degrees) * 60
        minutes = int(minutes_float)
        seconds = round((minutes_float - minutes) * 60)
        return f"{degrees}°{minutes}'{seconds}\" {direction}"
    return to_dms(lat, True), to_dms(lon, False)

def main():
    st.set_page_config(page_title="Ballon-Landepunkt-Prognose", layout="wide")
    st.title("🎈 Ballon-Landepunkt-Vorhersage")

    col_input, col_mode = st.columns(2)
    with col_input:
        eingabeart = st.radio("Eingabemethode", ["Interaktive Karte", "Manuelle Koordinaten"])
    with col_mode:
        modus = st.radio("Simulationsmodus", ["Vorwärts (Landepunkt bestimmen)", "Rückwärts (Startpunkt bestimmen)"])
    
    if eingabeart == "Interaktive Karte":
        st.markdown("Wähle den Punkt durch Klick auf die Karte:")
        start_location = [47.3769, 8.5417]
        m = folium.Map(location=start_location, zoom_start=6)
        map_data = st_folium(m, height=400)

        if map_data and map_data.get("last_clicked"):
            lat = map_data["last_clicked"]["lat"]
            lon = map_data["last_clicked"]["lng"]
            m = folium.Map(location=[lat, lon], zoom_start=8)
            folium.Marker([lat, lon], tooltip="Abstiegspunkt").add_to(m)
            st_folium(m, height=400)
            st.write(f"**Gewählter Punkt:** {lat:.5f}, {lon:.5f}")
        else:
            lat = start_location[0]
            lon = start_location[1]

        if map_data and map_data.get("last_clicked"):
            lat = map_data["last_clicked"]["lat"]
            lon = map_data["last_clicked"]["lng"]
        else:
            lat = start_location[0]
            lon = start_location[1]
    else:
        col_lat, col_lon = st.columns(2)
        with col_lat:
            lat = st.number_input("Breitengrad (dezimal)", value=47.3769)
        with col_lon:
            lon = st.number_input("Längengrad (dezimal)", value=8.5417)

    col_alt, col_rate, col_reduce = st.columns(3)
    with col_alt:
        altitude = st.number_input("Abstiegshöhe (m AMSL)", value=6000, min_value=100, max_value=30000)
    with col_rate:
        sinkrate = st.number_input("durchschnittliche Sinkrate (m/s)", value=4.5, min_value=0.1, max_value=10.0, step=0.1)
    with col_reduce:
        reduce_below = st.number_input("Sinkratenreduktion ab (m AGL)", value=300, min_value=0, max_value=2000)

    reduce_below = st.number_input("Sinkratenreduktion ab (m AGL)", value=300, min_value=0, max_value=2000)

    if st.button("Simulation starten"):
        icao_lat_input, icao_lon_input = decimal_to_icao(lat, lon)
        st.write(f"**Verwendete Koordinaten:** {icao_lat_input}, {icao_lon_input}")
        try:
            wind_speeds, wind_dirs, altitudes, model_time = fetch_gfs_profile(lat, lon)
            if modus.startswith("Vorwärts"):
                path, total_time = simulate_descent(lat, lon, altitude, sinkrate, wind_speeds, wind_dirs, altitudes, reduce_below)
            else:
                path, total_time = reverse_projection(lat, lon, altitude, sinkrate, wind_speeds, wind_dirs, altitudes, reduce_below)
            st.success(f"Simulation abgeschlossen. Dauer: {total_time/60:.1f} min")
            result_coords = path[-1] if modus.startswith("Vorwärts") else path[0]
            icao_lat, icao_lon = decimal_to_icao(result_coords[0], result_coords[1])
            st.markdown(f"**Zielkoordinaten:** {icao_lat}, {icao_lon}")
            gmap_url = f"https://www.google.com/maps?q={result_coords[0]},{result_coords[1]}"
            osm_url = f"https://www.openstreetmap.org/?mlat={result_coords[0]}&mlon={result_coords[1]}#map=15/{result_coords[0]}/{result_coords[1]}"
            st.markdown(f"[🌍 Google Maps öffnen]({gmap_url})  |  [🗺️ OpenStreetMap öffnen]({osm_url})")
            st.map(data={"lat": [p[0] for p in path], "lon": [p[1] for p in path]})
        except Exception as e:
            st.error(str(e))

if __name__ == "__main__":
    main()
