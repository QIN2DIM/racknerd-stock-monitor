from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from catalog import RackNerdCategory, SubscribedRackNerdCategory
from settings import settings


class ProductTask(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category_name: SubscribedRackNerdCategory
    category_url: str
    product_url: str
    pid: int | None = None
    store_title: str | None = None
    store_price_cycle: str | None = None
    store_card_text: str | None = None
    source: Literal["store", "seed"] = "store"


class DiskInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    raw: str
    size_value: float | None = None
    size_unit: str | None = None
    label: str | None = None


class LocationInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    raw: str
    normalized: str
    test_ip: str | None = None


class ServerSpecs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    cpu: str | None = None
    memory: str | None = None
    disks: list[DiskInfo] = Field(default_factory=list)
    monthly_transfer: str | None = None
    public_network_port: str | None = None
    raw_lines: list[str] = Field(default_factory=list)


class ServerInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category_name: SubscribedRackNerdCategory
    store_title: str
    model: str
    product_url: str
    confproduct_url: str
    pid: int
    store_price_cycle: str | None = None
    billing_cycle_annually_usd: float
    raw_locations: list[str] = Field(default_factory=list)
    normalized_locations: list[str] = Field(default_factory=list)
    location_options: list[LocationInfo] = Field(default_factory=list)
    specs: ServerSpecs
    updated_at: datetime
    store_card_text: str | None = None


class SnapshotFile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    updated_at: datetime
    source_categories: list[SubscribedRackNerdCategory] = Field(default_factory=list)
    item_count: int
    items: list[ServerInfo] = Field(default_factory=list)


class SavedPaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latest_path: Path
    history_path: Path


class ScraperConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscribed_categories: list[RackNerdCategory] = Field(
        default_factory=lambda: list(settings.subscribed_categories)
    )
    category_urls: list[str] = Field(default_factory=lambda: list(settings.category_urls))
    seed_confproduct_urls: list[str] = Field(
        default_factory=lambda: list(settings.seed_confproduct_urls)
    )
    max_concurrency: int = settings.max_concurrency
    timezone: str = settings.timezone
    output_dir: Path = settings.output_dir
    store_index_url: str = settings.store_index_url
    headless: bool = settings.headless
    scheduler_max_instances: int = settings.scheduler_max_instances
    scheduler_coalesce: bool = settings.scheduler_coalesce

    def scheduler_job_defaults(self) -> dict[str, bool | int]:
        return {"max_instances": self.scheduler_max_instances, "coalesce": self.scheduler_coalesce}
