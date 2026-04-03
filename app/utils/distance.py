"""
Distance calculation utilities using Haversine formula.
Calculates distances between geographic coordinates.
"""
import math
from typing import Tuple


def haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees) using Haversine formula.
    
    Args:
        lat1: Latitude of first point
        lon1: Longitude of first point
        lat2: Latitude of second point
        lon2: Longitude of second point
        
    Returns:
        Distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in kilometers
    r = 6371
    
    return c * r


def calculate_price(
    distance_km: float,
    base_price: float,
    price_per_km: float
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
    return base_price + (distance_km * price_per_km)


def calculate_commission(
    total_price: float,
    commission_percentage: float
) -> Tuple[float, float]:
    """
    Calculate platform commission and driver earnings.
    
    Args:
        total_price: Total trip price
        commission_percentage: Commission percentage (0-100)
        
    Returns:
        Tuple of (commission, driver_earnings)
    """
    commission = total_price * (commission_percentage / 100)
    driver_earnings = total_price - commission
    
    return round(commission, 2), round(driver_earnings, 2)


def estimate_duration(distance_km: float, avg_speed_kmh: float = 40) -> int:
    """
    Estimate trip duration based on distance and average speed.
    
    Args:
        distance_km: Distance in kilometers
        avg_speed_kmh: Average speed in km/h (default 40 km/h for city traffic)
        
    Returns:
        Estimated duration in minutes
    """
    hours = distance_km / avg_speed_kmh
    minutes = int(hours * 60)
    return max(minutes, 1)  # Minimum 1 minute
