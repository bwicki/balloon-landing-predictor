import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import requests


def wind_to_components(speed, direction_deg):
    direction_rad = np.deg2rad(direction_deg)
    u = -speed * np.sin(direction_rad)
    v = -speed * np.cos(direction_rad)
    return u, v


def simulate_descent(lat, lon, alt, sink_rate, wind_speed, wind_dir):
    dt = 10  # seconds
    path = [(lat, lon)]

    altitudes = np.arange(0, alt + 100, 100)
    wind_speeds = np.full_like(altitudes, wind_speed)
    wind_dirs = np.full_like(altitudes, wind_dir)

    while alt > 0:
        u = np.interp(alt, altitudes, [wind_to_components(s, d)[0] for s, d in zip(wind_speeds, wind_dirs)])
        v = np.interp(alt, altitudes, [wind_to_components(s, d)[1] for s, d in zip(wind_speeds, wind_dirs)])

        dx = u * dt
        dy = v * dt

        dlat = (dy / 111320)
        dlon = (dx / (40075000 * np.cos(np.deg2rad(lat)) / 360))

        lat += dlat
        lon += dlon
        alt -= sink_rate * dt

        path.append((lat, lon))

    return path


def fetch_gfs_wind(lat, lon):
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
    return ws, wd


def main():
    st.set_page_config(page_title="Ballon-Landepunkt-Prognose", layout="wide")
    st.title("\U0001F30D Ballon-Landepunkt-Vorhersage")

    st.markdown("""
    Dieses Tool berechnet den wahrscheinlichen Landepunkt eines Ballons,
    der einen Schnellabstieg aus hoher Höhe beginnt. Es verwendet aktuelle Winddaten (GFS, 100m-Niveau).
    """)

    if "last_path" not in st.session_state:
        st.session_state.last_path = None

    with st.form("input_form"):
        st.subheader("Eingabedaten")

        col1, col2 = st.columns(2)
        with col1:
            lat_value = st.number_input("Breitengrad (z.B. 47.37)", value=47.37)
            lat_dir = st.selectbox("N/S", ["N", "S"], index=0)
        with col2:
            lon_value = st.number_input("Längengrad (z.B. 8.55)", value=8.55)
            lon_dir = st.selectbox("E/W", ["E", "W"], index=0)

        alt = st.number_input("Abwurfhöhe in Metern", min_value=500, max_value=30000, value=6000, step=100)
        sink_rate = st.slider("Sinkrate (m/s)", min_value=1.5, max_value=6.0, value=4.5, step=0.1)
        submitted = st.form_submit_button("Simulation starten")

    if submitted:
        lat = lat_value if lat_dir == "N" else -lat_value
        lon = lon_value if lon_dir == "E" else -lon_value

        with st.spinner("Hole Winddaten und berechne Pfad ..."):
            try:
                wind_speed, wind_dir = fetch_gfs_wind(lat, lon)
                st.success(f"Wind: {wind_speed:.1f} m/s @ {wind_dir:.0f}°")
                path = simulate_descent(lat, lon, alt, sink_rate, wind_speed, wind_dir)
                st.session_state.last_path = path
            except Exception as e:
                st.error(f"Fehler bei der Simulation: {e}")

    if st.session_state.last_path:
        path = st.session_state.last_path
        st.markdown("### Ergebnis")
        st.write(f"Letzter Punkt (Landepunkt): {path[-1]}")

        fmap = folium.Map(location=path[0], zoom_start=9)
        folium.Marker(path[0], tooltip="Abwurfpunkt", icon=folium.Icon(color="green")).add_to(fmap)
        folium.Marker(path[-1], tooltip="Landepunkt", icon=folium.Icon(color="red")).add_to(fmap)
        folium.PolyLine(path, color="blue", weight=2.5, opacity=0.8).add_to(fmap)

        st_folium(fmap, height=600, width=1000)


if __name__ == "__main__":
    main()
