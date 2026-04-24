"""Decode Google Encoded Polyline Algorithm Format → (lat, lng) degrees."""

from typing import List, Tuple


def decode_google_polyline(encoded: str) -> List[Tuple[float, float]]:
    if not encoded:
        return []
    index = 0
    lat = 0
    lng = 0
    coordinates: List[Tuple[float, float]] = []

    while index < len(encoded):
        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        coordinates.append((lat * 1e-5, lng * 1e-5))

    return coordinates
