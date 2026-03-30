from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    plex_url: str = ""
    plex_token: str = ""
    plex_library_name: str = "Music"
    music_dir: str = ""
    genius_api_key: str = ""
    scan_interval_minutes: int = 30
    port: int = 8000


settings = Settings()
