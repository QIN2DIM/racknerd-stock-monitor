from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from deploy import start_scheduler
from racknerd.models import ScraperConfig
from racknerd.scraper import run_snapshot
from racknerd.storage import save_snapshot
from settings import settings

app = typer.Typer(help="RackNerd stock monitor CLI.", no_args_is_help=True)


def resolve_headless(headed: bool, headless: bool) -> bool:
    browser_headless = settings.headless
    if headed:
        browser_headless = False
    if headless:
        browser_headless = True
    return browser_headless


async def run_snapshot_command(
    category_urls: list[str] | None = None,
    seed_confproduct_urls: list[str] | None = None,
    store_index_url: str = settings.store_index_url,
    max_concurrency: int = settings.max_concurrency,
    timezone: str = settings.timezone,
    output_dir: Path = settings.output_dir,
    headed: bool = False,
    headless: bool = False,
) -> None:
    config = ScraperConfig(
        category_urls=category_urls or list(settings.category_urls),
        seed_confproduct_urls=seed_confproduct_urls or list(settings.seed_confproduct_urls),
        store_index_url=store_index_url,
        max_concurrency=max_concurrency,
        timezone=timezone,
        output_dir=output_dir,
        headless=resolve_headless(headed, headless),
    )

    progress = Progress(
        SpinnerColumn(spinner_name="line"),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    )
    discovery_task_id = progress.add_task("Discovering product queue...", total=None)
    category_task_ids: dict[str, int] = {}

    def on_queue_discovered(category_groups: list[tuple[str, list]]) -> None:
        total_products = sum(len(tasks) for _, tasks in category_groups)
        progress.update(
            discovery_task_id,
            description=f"Discovered {len(category_groups)} categories / {total_products} products.",
        )
        for category_name, tasks in category_groups:
            category_task_ids[category_name] = progress.add_task(
                f"{category_name} [0/{len(tasks)}]", total=len(tasks)
            )

    def on_scrape_progress(category_name: str, completed: int, total: int, task, result) -> None:
        del task, result
        task_id = category_task_ids.get(category_name)
        if task_id is None:
            task_id = progress.add_task(f"{category_name} [0/{total}]", total=total)
            category_task_ids[category_name] = task_id
        progress.update(
            task_id,
            completed=completed,
            total=total,
            description=f"{category_name} [{completed}/{total}]",
        )

    with progress:
        snapshot = await run_snapshot(
            config, queue_callback=on_queue_discovered, progress_callback=on_scrape_progress
        )

    saved_paths = save_snapshot(snapshot, config.output_dir)
    typer.secho(f"Scraped {snapshot.item_count} items", fg=typer.colors.GREEN)
    typer.echo(f"Latest snapshot: {saved_paths.latest_path}")
    typer.echo(f"History snapshot: {saved_paths.history_path}")


def run_scheduler_command(
    interval_minutes: int = settings.scheduler_interval_minutes,
    run_immediately: bool = settings.scheduler_run_immediately,
    headed: bool = False,
    headless: bool = False,
) -> None:
    config = ScraperConfig(headless=resolve_headless(headed, headless))
    start_scheduler(config, interval_minutes=interval_minutes, run_immediately=run_immediately)


@app.command("snapshot")
def snapshot_cli(
    category_urls: list[str] | None = typer.Option(
        None,
        "--category-url",
        help="Override target category URLs. Repeat the option to pass multiple values.",
    ),
    seed_confproduct_urls: list[str] | None = typer.Option(
        None,
        "--seed-confproduct-url",
        help="Directly scrape one or more confproduct URLs for debugging.",
    ),
    store_index_url: str = typer.Option(
        settings.store_index_url,
        "--store-index-url",
        help="Store page used to discover target categories when category URLs are not provided.",
    ),
    max_concurrency: int = typer.Option(
        settings.max_concurrency,
        "--max-concurrency",
        help="Maximum number of concurrent product detail pages.",
    ),
    timezone: str = typer.Option(
        settings.timezone, "--timezone", help="Timezone used for snapshot timestamps."
    ),
    output_dir: Path = typer.Option(
        settings.output_dir,
        "--output-dir",
        help="Directory used for latest/history JSON snapshots.",
    ),
    headed: bool = typer.Option(
        False, "--headed", help="Launch Chromium in headed mode for debugging."
    ),
    headless: bool = typer.Option(False, "--headless", help="Force Chromium headless mode."),
) -> None:
    asyncio.run(
        run_snapshot_command(
            category_urls=category_urls,
            seed_confproduct_urls=seed_confproduct_urls,
            store_index_url=store_index_url,
            max_concurrency=max_concurrency,
            timezone=timezone,
            output_dir=output_dir,
            headed=headed,
            headless=headless,
        )
    )


@app.command("scheduler")
def scheduler_cli(
    interval_minutes: int = typer.Option(
        settings.scheduler_interval_minutes,
        "--interval-minutes",
        help="How often to run the stock snapshot job.",
    ),
    run_immediately: bool = typer.Option(
        settings.scheduler_run_immediately,
        "--run-immediately",
        help="Run one snapshot immediately before entering the interval loop.",
    ),
    headed: bool = typer.Option(
        False, "--headed", help="Launch Chromium in headed mode for debugging."
    ),
    headless: bool = typer.Option(False, "--headless", help="Force Chromium headless mode."),
) -> None:
    run_scheduler_command(
        interval_minutes=interval_minutes,
        run_immediately=run_immediately,
        headed=headed,
        headless=headless,
    )


def main() -> None:
    app()
