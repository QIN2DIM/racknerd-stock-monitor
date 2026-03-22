from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from racknerd.models import ScraperConfig
from racknerd.scraper import run_snapshot
from racknerd.storage import save_snapshot
from settings import settings


async def _snapshot_job(config: ScraperConfig) -> None:
    snapshot = await run_snapshot(config)
    saved_paths = save_snapshot(snapshot, config.output_dir)
    print(f"Scraped {snapshot.item_count} items")
    print(f"Latest snapshot: {saved_paths.latest_path}")
    print(f"History snapshot: {saved_paths.history_path}")


def start_scheduler(
    config: ScraperConfig | None = None,
    *,
    interval_minutes: int | None = None,
    run_immediately: bool | None = None,
) -> None:
    scraper_config = config or ScraperConfig()
    scheduler = AsyncIOScheduler(
        timezone=scraper_config.timezone,
        job_defaults=scraper_config.scheduler_job_defaults(),
    )
    scheduler.add_job(
        _snapshot_job,
        trigger="interval",
        minutes=interval_minutes or settings.scheduler_interval_minutes,
        args=[scraper_config],
        id="racknerd-stock-snapshot",
        replace_existing=True,
    )

    async def runner() -> None:
        if run_immediately if run_immediately is not None else settings.scheduler_run_immediately:
            await _snapshot_job(scraper_config)
        scheduler.start()
        try:
            await asyncio.Event().wait()
        finally:
            scheduler.shutdown(wait=False)

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        pass
