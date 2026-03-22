from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from racknerd.catalog import DEFAULT_SUBSCRIBED_CATEGORIES, RackNerdCategory

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path(__file__).parent / ".env", BASE_DIR / ".env"),
        env_ignore_empty=True,
        extra="ignore",
        env_prefix="RSM_",
    )

    store_index_url: str = "https://my.racknerd.com/index.php?rp=/store/blackfriday2025"
    subscribed_categories: list[RackNerdCategory] = Field(
        default_factory=lambda: list(DEFAULT_SUBSCRIBED_CATEGORIES)
    )
    category_urls: list[str] = Field(default_factory=list)
    seed_confproduct_urls: list[str] = Field(default_factory=list)
    max_concurrency: int = 3
    timezone: str = "Asia/Shanghai"
    output_dir: Path = BASE_DIR / "data"
    headless: bool = True
    scheduler_max_instances: int = 1
    scheduler_coalesce: bool = True
    scheduler_interval_minutes: int = 60
    scheduler_run_immediately: bool = False


settings = Settings()
