"""
Geospatial utility functions for distance and location calculations.
"""
import math
from typing import Tuple


def calculate_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Calculate distance between two coordinates using Haversine formula.
    
    Args:
        lat1: Latitude of first point
        lon1: Longitude of first point
        lat2: Latitude of second point
        lon2: Longitude of second point
    
    Returns:
        Distance in kilometers
    """
    # Earth's radius in kilometers
    R = 6371.0
    
    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance = R * c
    return distance


def calculate_price(
    distance_km: float,
    base_price: float = 2.0,
    price_per_km: float = 1.5
) -> float:
    """
    Calculate trip price based on distance.
    
    Args:
        distance_km: Distance in kilometers
        base_price: Base fare
        price_per_km: Price per kilometer
    
    Returns:
        Total price
    """
    # region agent log
    try:
        import json, time  # noqa
        with open("debug-4d6510.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({
                "sessionId": "4d6510",
                "runId": "pre-fix",
                "hypothesisId": "H1",
                "location": "app/utils/geo.py:calculate_price",
                "message": "legacy_calculate_price_called",
                "data": {"distance_km": float(distance_km)},
                "timestamp": int(time.time() * 1000),
            }) + "\n")
    except Exception:
        pass
    # endregion
    return round(base_price + (distance_km * price_per_km), 2)


def calculate_commission(
    total_price: float,
    commission_rate: float = 0.15
) -> Tuple[float, float]:
    """
    Calculate platform commission and driver earnings.
    
    Args:
        total_price: Total trip price
        commission_rate: Commission rate (default 15%)
    
    Returns:
        Tuple of (commission_amount, driver_earnings)
    """
    commission = round(total_price * commission_rate, 2)
    driver_earnings = round(total_price - commission, 2)
    return commission, driver_earnings


def is_within_radius(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    radius_km: float
) -> bool:
    """
    Check if two points are within a specified radius.
    
    Args:
        lat1: Latitude of first point
        lon1: Longitude of first point
        lat2: Latitude of second point
        lon2: Longitude of second point
        radius_km: Radius in kilometers
    
    Returns:
        True if points are within radius
    """
    distance = calculate_distance(lat1, lon1, lat2, lon2)
    return distance <= radius_km


def format_location(latitude: float, longitude: float) -> str:
    """Format coordinates as a readable string"""
    return f"{latitude:.6f}, {longitude:.6f}"


def validate_coordinates(latitude: float, longitude: float) -> bool:
    """
    Validate geographic coordinates.
    
    Args:
        latitude: Latitude value
        longitude: Longitude value
    
    Returns:
        True if coordinates are valid
    """
    return -90 <= latitude <= 90 and -180 <= longitude <= 180
