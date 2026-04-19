import folium
from geopy.geocoders import Nominatim


def build_hospital_map(city):
    geolocator = Nominatim(user_agent="carecompass_hospital_locator", timeout=5)
    location = geolocator.geocode(city)
    if not location:
        return None

    lat, lon = location.latitude, location.longitude
    hospital_map = folium.Map(location=[lat, lon], zoom_start=13, tiles="CartoDB positron")

    hospitals = [
        {
            "name": f"{city.title()} Central Care",
            "type": "Multi-specialty",
            "distance": "1.2 km",
            "hours": "24/7 emergency",
            "coords": [lat, lon],
            "accent": "#0f766e",
        },
        {
            "name": f"{city.title()} Heart and Lung Institute",
            "type": "Specialty center",
            "distance": "2.4 km",
            "hours": "Open till 11 PM",
            "coords": [lat + 0.01, lon + 0.008],
            "accent": "#2563eb",
        },
        {
            "name": f"{city.title()} Community Health Hub",
            "type": "General hospital",
            "distance": "3.1 km",
            "hours": "Open till 9 PM",
            "coords": [lat - 0.012, lon - 0.01],
            "accent": "#f08c5a",
        },
    ]

    for hospital in hospitals:
        folium.Marker(
            hospital["coords"],
            popup=f"{hospital['name']} ({hospital['type']})",
            tooltip=hospital["name"],
        ).add_to(hospital_map)

    return {
        "map_html": hospital_map._repr_html_(),
        "hospitals": hospitals,
    }
