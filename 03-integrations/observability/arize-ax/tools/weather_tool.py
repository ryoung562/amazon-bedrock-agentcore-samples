"""Weather tool returning mock weather data for demonstration."""

import logging
import random
from typing import Any

logger = logging.getLogger(__name__)

MOCK_WEATHER_DATA: dict[str, dict[str, Any]] = {
    "new york": {"temperature": 72, "conditions": "Partly Cloudy", "humidity": 65},
    "london": {"temperature": 59, "conditions": "Rainy", "humidity": 80},
    "tokyo": {"temperature": 68, "conditions": "Clear", "humidity": 55},
    "paris": {"temperature": 64, "conditions": "Cloudy", "humidity": 70},
    "sydney": {"temperature": 75, "conditions": "Sunny", "humidity": 60},
    "berlin": {"temperature": 61, "conditions": "Partly Cloudy", "humidity": 68},
    "mumbai": {"temperature": 86, "conditions": "Humid", "humidity": 85},
    "toronto": {"temperature": 66, "conditions": "Clear", "humidity": 58},
    "singapore": {"temperature": 88, "conditions": "Humid", "humidity": 90},
    "dubai": {"temperature": 95, "conditions": "Sunny", "humidity": 45},
}


def get_weather(city: str) -> dict[str, Any]:
    """Get current weather information for a city.

    Args:
        city: The name of the city to get weather for

    Returns:
        Dictionary containing weather information
    """
    if not city or not isinstance(city, str):
        raise ValueError("City name must be a non-empty string")

    city_normalized = city.strip().lower()
    if not city_normalized:
        raise ValueError("City name cannot be empty")

    logger.info("Getting weather for city: %s", city_normalized)

    if city_normalized in MOCK_WEATHER_DATA:
        weather_data = MOCK_WEATHER_DATA[city_normalized]
    else:
        conditions_list = ["Sunny", "Cloudy", "Partly Cloudy", "Rainy", "Clear"]
        weather_data = {
            "temperature": random.randint(50, 95),  # nosec B311
            "conditions": random.choice(conditions_list),  # nosec B311
            "humidity": random.randint(40, 90),  # nosec B311
        }

    return {
        "city": city.title(),
        "temperature_f": weather_data["temperature"],
        "conditions": weather_data["conditions"],
        "humidity_percent": weather_data["humidity"],
    }
