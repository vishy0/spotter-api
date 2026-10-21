import sys
from pathlib import Path
from django.apps import AppConfig
from django.conf import settings


class FuelRouterConfig(AppConfig):
    name = "fuel_router"

    def ready(self):
        # Avoid running data loading during non-server management commands (e.g. makemigrations)
        # but ensure it runs during test and runserver
        from fuel_router.services.spatial import spatial_index

        data_dir = Path(settings.BASE_DIR) / "data"
        cities_csv = data_dir / "us_cities.csv"
        fuel_csv = data_dir / "fuel_prices.csv"

        if cities_csv.exists() and fuel_csv.exists():
            count = spatial_index.load(cities_csv, fuel_csv)
            print(f"Loaded {count} stations.")
