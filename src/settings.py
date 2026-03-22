from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from catalog import DEFAULT_SUBSCRIBED_CATEGORIES, RackNerdCategory

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path(__file__).parent / ".env", BASE_DIR / ".env"),
        env_ignore_empty=True,
        extra="ignore",
        env_prefix="RSM_",
    )

    store_index_url: str = Field(
        default="https://my.racknerd.com/index.php?rp=/store/blackfriday2025",
        description="用于发现商店分类入口的 RackNerd 商店页面 URL。",
    )
    subscribed_categories: list[RackNerdCategory] = Field(
        default_factory=lambda: list(DEFAULT_SUBSCRIBED_CATEGORIES),
        description="实际订阅并采集的 RackNerd 商城分类列表。",
    )
    category_urls: list[str] = Field(
        default_factory=list, description="显式指定要采集的分类 URL；非空时优先于自动分类发现。"
    )
    seed_confproduct_urls: list[str] = Field(
        default_factory=list,
        description="用于调试的 confproduct 直链列表；非空时跳过商店分类发现。",
    )
    max_concurrency: int = Field(default=3, description="详情页抓取共享并发数上限。")
    timezone: str = Field(default="Asia/Shanghai", description="快照时间戳和调度器使用的时区。")
    output_dir: Path = Field(default=BASE_DIR / "data", description="快照 JSON 输出目录。")
    headless: bool = Field(default=True, description="是否以无头模式启动浏览器。")
    scheduler_max_instances: int = Field(
        default=1, description="APScheduler 允许的同一任务最大并发实例数。"
    )
    scheduler_coalesce: bool = Field(default=True, description="调度积压时是否合并错过的任务执行。")
    scheduler_interval_minutes: int = Field(
        default=600, description="定时采集任务的执行间隔，单位为分钟。"
    )
    scheduler_run_immediately: bool = Field(
        default=False, description="启动调度器后是否立即先执行一次采集任务。"
    )


settings = Settings()
