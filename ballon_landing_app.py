import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import requests
from datetime import datetime

# Höhenabfrage (Open-Elevation)
# GFS Windprofil von Open-Meteo API

def fetch_gfs_profile(lat, lon):
    try:
        now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=wind_speed_100m,wind_direction_100m&models=gfs&timezone=UTC"
        response = requests.get(url, timeout=10)
        data = response.json()

        if 'hourly' not in data or 'wind_speed_100m' not in data['hourly']:
            raise RuntimeError("Die GFS-Antwort enthält keine gültigen Winddaten.")

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

import plotly.graph_objects as go

# Hinweis: matplotlib wurde entfernt, da es im aktuellen Sandbox-Umfeld nicht verfügbar ist.

def show_wind_profile(wind_speeds, altitudes, model_time):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=wind_speeds,
        y=altitudes,
        mode='lines+markers',
        name='Windgeschwindigkeit',
        line=dict(color='blue')
    ))
    fig.update_layout(
        title=f"Vertikales Windprofil (GFS) – Modelllauf: {model_time}",
        xaxis_title="Windgeschwindigkeit (m/s)",
        yaxis_title="Höhe (m AMSL)",
        yaxis=dict(autorange='reversed'),
        height=400
    )
    st.plotly_chart(fig, use_container_width=True)
