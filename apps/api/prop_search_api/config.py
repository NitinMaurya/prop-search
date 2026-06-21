"""Environment config. See apps/api/.env.example."""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Settings:
    database_url: str = os.environ.get("DATABASE_URL", "")
    jwt_secret: str = os.environ.get("SUPABASE_JWT_SECRET", "")
    # Comma-separated allowed web origins for CORS.
    web_origins: list[str] = [
        o.strip() for o in os.environ.get("WEB_ORIGIN", "http://localhost:3000").split(",")
        if o.strip()
    ]


settings = Settings()
