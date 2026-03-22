from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Callable, Iterable, Sequence
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from settings import settings

from catalog import RackNerdCategory
from racknerd.models import (
    DiskInfo,
    LocationInfo,
    ProductTask,
    ScraperConfig,
    ServerInfo,
    ServerSpecs,
    SnapshotFile,
)

CategoryTaskGroup = tuple[str, list[ProductTask]]
QueueDiscoveredCallback = Callable[[list[CategoryTaskGroup]], None]
ScrapeProgressCallback = Callable[[str, int, int, ProductTask, ServerInfo | None], None]

CATEGORY_LINK_XPATH = "//a[contains(@href, 'rp=/store/')]"
PRODUCT_CARD_XPATH = (
    "//div[@id='order-standard_cart']//div"
    "[contains(concat(' ', normalize-space(@class), ' '), ' product ')]"
    "[.//a[contains(@class,'btn-order-now')]]"
)
ANNUAL_PRODUCT_CARD_XPATH = (
    PRODUCT_CARD_XPATH + "[.//footer[contains(normalize-space(.), 'Annually')]]"
)
CATEGORY_TITLE_XPATH = "//div[@id='order-standard_cart']//h1[1] | //h1[1]"
PRODUCT_TITLE_XPATH = "//p[contains(@class,'product-title')]"
PRODUCT_DESCRIPTION_XPATH = "//p[contains(@class,'product-description')]"
PRODUCT_GROUP_XPATH = (
    "//span[contains(@class,'product-group')] | //div[contains(@class,'product-group')]"
)
BILLING_SELECT_XPATH = "//label[normalize-space()='Choose Billing Cycle']/following::select[1]"
LOCATION_SELECT_XPATH = "//label[normalize-space()='Location']/following-sibling::select[1]"

PRICE_PATTERN = re.compile(r"\$(?P<amount>\d+(?:\.\d+)?)\s*USD", re.IGNORECASE)
TEST_IP_PATTERN = re.compile(r"Test IP:\s*([0-9.]+)", re.IGNORECASE)
SIZE_PATTERN = re.compile(r"(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>GB|TB)\b", re.IGNORECASE)


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = re.sub(r"[ \t]+", " ", value)
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    return collapsed.strip() or None


def normalize_multiline(value: str | None) -> str | None:
    if value is None:
        return None
    lines = [normalize_text(line) for line in value.splitlines()]
    filtered = [line for line in lines if line]
    if not filtered:
        return None
    return "\n".join(filtered)


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def parse_usd_amount(text: str) -> float | None:
    match = PRICE_PATTERN.search(text)
    if not match:
        return None
    return float(match.group("amount"))


def normalize_location_name(raw: str) -> str:
    location = TEST_IP_PATTERN.sub("", raw)
    location = re.sub(r"\([^)]*\)", "", location)
    location = normalize_text(location) or raw
    location = re.sub(r"\bDC[-\s]?0?2\b", "DC-02", location, flags=re.IGNORECASE)
    location = re.sub(r"\bDC[-\s]?0?3\b", "DC-03", location, flags=re.IGNORECASE)
    return location


def parse_location_option(raw: str) -> LocationInfo:
    test_ip_match = TEST_IP_PATTERN.search(raw)
    return LocationInfo(
        raw=normalize_text(raw) or raw,
        normalized=normalize_location_name(raw),
        test_ip=test_ip_match.group(1) if test_ip_match else None,
    )


def build_model_name(category_name: str, confproduct_title: str) -> str:
    title = normalize_text(confproduct_title) or confproduct_title
    if category_name and category_name.lower() not in title.lower() and len(title) <= 24:
        return f"{category_name} - {title}"
    return title


def parse_disk_line(line: str) -> DiskInfo:
    match = SIZE_PATTERN.search(line)
    if not match:
        return DiskInfo(raw=line)
    label = normalize_text(line.replace(match.group(0), "", 1))
    return DiskInfo(
        raw=line,
        size_value=float(match.group("size")),
        size_unit=match.group("unit").upper(),
        label=label,
    )


def parse_server_specs(description_text: str | None) -> ServerSpecs:
    normalized = normalize_multiline(description_text)
    lines = normalized.splitlines() if normalized else []
    cpu = None
    memory = None
    disks: list[DiskInfo] = []
    monthly_transfer = None
    public_network_port = None

    for line in lines:
        lower = line.lower()
        if cpu is None and ("vcpu" in lower or "cpu core" in lower or "amd ryzen cpu" in lower):
            cpu = line
            continue
        if memory is None and re.search(r"\bram\b", lower):
            memory = line
            continue
        if "network port" in lower and public_network_port is None:
            public_network_port = line
            continue
        if (
            monthly_transfer is None
            and ("bandwidth" in lower or "transfer" in lower)
        ):
            monthly_transfer = line
            continue
        if "storage" in lower or "ssd" in lower or "nvme" in lower or "hdd" in lower:
            disks.append(parse_disk_line(line))

    return ServerSpecs(
        cpu=cpu,
        memory=memory,
        disks=disks,
        monthly_transfer=monthly_transfer,
        public_network_port=public_network_port,
        raw_lines=lines,
    )


def is_server_like_card(description_text: str | None) -> bool:
    if not description_text:
        return False
    lower = description_text.lower()
    has_cpu = "vcpu" in lower or "cpu core" in lower or "amd ryzen cpu" in lower
    has_memory = bool(re.search(r"\bram\b", lower))
    has_network_port = "network port" in lower
    return has_cpu and has_memory and has_network_port


async def _locator_text(locator) -> str | None:
    if await locator.count() == 0:
        return None
    return normalize_text(await locator.first.text_content())


async def _locator_inner_text(locator) -> str | None:
    if await locator.count() == 0:
        return None
    return normalize_multiline(await locator.first.inner_text())


async def _extract_select_option_texts(select_locator) -> list[str]:
    if await select_locator.count() == 0:
        return []
    options = select_locator.first.locator("xpath=./option")
    texts = await options.all_text_contents()
    return [normalize_text(text) for text in texts if normalize_text(text)]


async def discover_target_category_urls(
    page: Page, store_index_url: str, subscribed_categories: Sequence[RackNerdCategory]
) -> list[str]:
    await page.goto(store_index_url, wait_until="domcontentloaded")
    await page.wait_for_selector(f"xpath={CATEGORY_LINK_XPATH}", state="attached")
    links = page.locator(f"xpath={CATEGORY_LINK_XPATH}")
    count = await links.count()
    urls: list[str] = []
    subscribed = set(subscribed_categories)
    for index in range(count):
        link = links.nth(index)
        title = normalize_text(await link.text_content())
        href = await link.get_attribute("href")
        if not title or not href:
            continue
        if title in subscribed:
            urls.append(urljoin(page.url, href))
    return dedupe_preserve_order(urls)


async def extract_product_tasks_from_page(
    page: Page, category_name: str, category_url: str
) -> list[ProductTask]:
    cards = page.locator(f"xpath={ANNUAL_PRODUCT_CARD_XPATH}")
    count = await cards.count()
    tasks: list[ProductTask] = []
    for index in range(count):
        card = cards.nth(index)
        title = await _locator_text(card.locator("xpath=.//header//span[1]"))
        order_button = card.locator("xpath=.//a[contains(@class,'btn-order-now')]")
        href = await order_button.get_attribute("href")
        button_id = await order_button.get_attribute("id")
        
        pid = None
        if button_id:
            # product20-order-button -> 20
            match = re.search(r"product(\d+)", button_id)
            if match:
                pid = int(match.group(1))
        
        if pid is None and href:
            # cart.php?a=add&pid=20 -> 20
            match = re.search(r"pid=(\d+)", href)
            if match:
                pid = int(match.group(1))

        footer_text = await _locator_inner_text(card.locator("xpath=.//footer"))
        desc_text = await _locator_inner_text(
            card.locator("xpath=.//div[contains(@class,'product-desc')]")
        )
        if (
            not href
            or not footer_text
            or "Annually" not in footer_text
            or not is_server_like_card(desc_text)
            or pid is None
        ):
            continue
        tasks.append(
            ProductTask(
                category_name=category_name,
                category_url=category_url,
                product_url=urljoin(category_url, href),
                pid=pid,
                store_title=title,
                store_price_cycle="Annually",
                store_card_text=desc_text,
            )
        )
    return tasks


async def discover_product_tasks(
    browser: BrowserContext,
    category_urls: Sequence[str],
    *,
    subscribed_categories: Sequence[RackNerdCategory] | None = None,
    store_index_url: str | None = None,
) -> list[ProductTask]:
    groups = await discover_product_task_groups(
        browser,
        category_urls,
        subscribed_categories=subscribed_categories,
        store_index_url=store_index_url,
    )
    return [task for _, tasks in groups for task in tasks]


async def discover_product_task_groups(
    browser: BrowserContext,
    category_urls: Sequence[str],
    *,
    subscribed_categories: Sequence[RackNerdCategory] | None = None,
    store_index_url: str | None = None,
) -> list[CategoryTaskGroup]:
    page = await browser.new_page()
    try:
        urls = list(category_urls)
        if not urls:
            urls = await discover_target_category_urls(
                page,
                store_index_url or settings.store_index_url,
                subscribed_categories or settings.subscribed_categories,
            )

        groups: list[CategoryTaskGroup] = []
        seen_urls: set[str] = set()
        for category_url in urls:
            await page.goto(category_url, wait_until="domcontentloaded")
            await page.wait_for_selector(f"xpath={PRODUCT_CARD_XPATH}")
            category_name = (
                await _locator_text(page.locator(f"xpath={CATEGORY_TITLE_XPATH}")) or category_url
            )
            category_tasks: list[ProductTask] = []
            for task in await extract_product_tasks_from_page(page, category_name, category_url):
                if task.product_url in seen_urls:
                    continue
                seen_urls.add(task.product_url)
                category_tasks.append(task)
            if category_tasks:
                groups.append((category_name, category_tasks))
        return groups
    finally:
        await page.close()


async def extract_server_info_from_page(
    page: Page, task: ProductTask, updated_at: datetime
) -> ServerInfo | None:
    await page.wait_for_selector(f"xpath={PRODUCT_TITLE_XPATH}", timeout=15_000)

    confproduct_url = page.url
    confproduct_title = (
        await _locator_text(page.locator(f"xpath={PRODUCT_TITLE_XPATH}")) or task.store_title
    )
    if not confproduct_title:
        return None

    description_text = await _locator_inner_text(page.locator(f"xpath={PRODUCT_DESCRIPTION_XPATH}"))
    billing_select = page.locator(f"xpath={BILLING_SELECT_XPATH}")
    billing_options = await _extract_select_option_texts(billing_select)
    annual_price = next(
        (parse_usd_amount(text) for text in billing_options if "Annually" in text), None
    )
    if annual_price is None:
        return None

    location_select = page.locator(f"xpath={LOCATION_SELECT_XPATH}")
    location_options = [
        parse_location_option(text) for text in await _extract_select_option_texts(location_select)
    ]
    raw_locations = [option.raw for option in location_options]
    normalized_locations = dedupe_preserve_order(option.normalized for option in location_options)

    category_name = task.category_name
    if task.source == "seed":
        inferred_category = await _locator_text(page.locator(f"xpath={PRODUCT_GROUP_XPATH}"))
        if inferred_category:
            category_name = inferred_category

    return ServerInfo(
        category_name=category_name,
        store_title=task.store_title or confproduct_title,
        model=build_model_name(category_name, confproduct_title),
        product_url=task.product_url,
        confproduct_url=confproduct_url,
        pid=task.pid or 0,  # Fallback to 0 if unknown for seed tasks
        store_price_cycle=task.store_price_cycle,
        billing_cycle_annually_usd=annual_price,
        raw_locations=raw_locations,
        normalized_locations=normalized_locations,
        location_options=location_options,
        specs=parse_server_specs(description_text or task.store_card_text),
        updated_at=updated_at,
        store_card_text=task.store_card_text,
    )


async def scrape_server_info(
    browser: BrowserContext,
    task: ProductTask,
    semaphore: asyncio.Semaphore | None = None,
    *,
    updated_at: datetime | None = None,
) -> ServerInfo | None:
    timestamp = updated_at or datetime.now(ZoneInfo(settings.timezone))
    if semaphore is not None:
        async with semaphore:
            return await scrape_server_info(browser, task, updated_at=timestamp)

    page = await browser.new_page()
    try:
        await page.goto(task.product_url, wait_until="domcontentloaded")
        return await extract_server_info_from_page(page, task, timestamp)
    except PlaywrightTimeoutError:
        print(f"Skipping non-confproduct page: {task.product_url}")
        return None
    except Exception as exc:
        print(f"Failed to scrape {task.product_url}: {exc}")
        return None
    finally:
        await page.close()


async def collect_server_info(
    browser: BrowserContext,
    category_groups: Sequence[CategoryTaskGroup],
    *,
    max_concurrency: int,
    updated_at: datetime,
    progress_callback: ScrapeProgressCallback | None = None,
) -> list[ServerInfo]:
    semaphore = asyncio.Semaphore(max_concurrency)
    items: list[ServerInfo] = []
    totals = {category_name: len(tasks) for category_name, tasks in category_groups}
    completed_by_category = {category_name: 0 for category_name, _ in category_groups}

    async def scrape_task(task: ProductTask) -> tuple[ProductTask, ServerInfo | None]:
        result = await scrape_server_info(browser, task, semaphore=semaphore, updated_at=updated_at)
        return task, result

    futures: list[asyncio.Task[tuple[ProductTask, ServerInfo | None]]] = []
    for category_name, tasks in category_groups:
        for task in tasks:
            future = asyncio.create_task(scrape_task(task))
            futures.append(future)

    for future in asyncio.as_completed(futures):
        task, result = await future
        category_name = task.category_name
        completed_by_category[category_name] += 1
        if progress_callback is not None:
            progress_callback(
                category_name,
                completed_by_category[category_name],
                totals[category_name],
                task,
                result,
            )
        if result is not None:
            items.append(result)
    return items


async def run_snapshot(
    config: ScraperConfig,
    *,
    queue_callback: QueueDiscoveredCallback | None = None,
    progress_callback: ScrapeProgressCallback | None = None,
) -> SnapshotFile:
    updated_at = datetime.now(ZoneInfo(config.timezone))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=config.headless)
        context = await browser.new_context()
        try:
            if config.seed_confproduct_urls:
                category_groups = [
                    (
                        "seed",
                        [
                            ProductTask(
                                category_name="seed",
                                category_url=url,
                                product_url=url,
                                source="seed",
                            )
                            for url in config.seed_confproduct_urls
                        ],
                    )
                ]
            else:
                category_groups = await discover_product_task_groups(
                    context,
                    config.category_urls,
                    subscribed_categories=config.subscribed_categories,
                    store_index_url=config.store_index_url,
                )
            if queue_callback is not None:
                queue_callback(category_groups)
            items = await collect_server_info(
                context,
                category_groups,
                max_concurrency=config.max_concurrency,
                updated_at=updated_at,
                progress_callback=progress_callback,
            )
        finally:
            await context.close()
            await browser.close()

    source_categories = [category_name for category_name, _ in category_groups]
    return SnapshotFile(
        updated_at=updated_at,
        source_categories=source_categories,
        item_count=len(items),
        items=items,
    )
