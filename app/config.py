from decouple import config

# Scraper configuration
SCRAPER_CONFIG = {
    "past_period": 60,  # minutes
    "page_size": 20,
    "max_concurrent": 20,
    "run_interval": 30,  # minutes between each run
}

POSTGRES_CONFIG = {
    "host": config("POSTGRES_HOST", default="localhost"),
    "port": config("POSTGRES_PORT", default=6500),
    "user": config("POSTGRES_USER", default="muhammad"),
    "password": config("POSTGRES_PASSWORD", default="muhammad"),
    "database": config("POSTGRES_DATABASE", default="taholding"),
}

OPENAI_API_KEY = config("OPENAI_API_KEY", default="") 