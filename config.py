from decouple import config

# Scraper configuration
SCRAPER_CONFIG = {
    "past_period": 60,  # minutes
    "page_size": 20,
    "max_concurrent": 20,
    "run_interval": 60,  # minutes between each run
}

POSTGRES_CONFIG = {
    "host": "localhost",
    "port": 6500,
    "user": "muhammad",
    "password": "muhammad",
    "database": "taholding",
}

OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
