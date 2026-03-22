from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from racknerd import DiskInfo, ProductTask, ScraperConfig, ServerInfo, ServerSpecs, SnapshotFile
from racknerd.scraper import (
    discover_target_category_urls,
    extract_product_tasks_from_page,
    extract_server_info_from_page,
    normalize_location_name,
    parse_server_specs,
    run_snapshot,
)
from racknerd import save_snapshot

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class ParsingTests(unittest.TestCase):
    def test_normalize_location_variants(self) -> None:
        self.assertEqual(
            normalize_location_name("Los Angeles DC03 (Test IP: 107.174.51.158)"),
            "Los Angeles DC-03",
        )
        self.assertEqual(
            normalize_location_name("Los Angeles DC02 (Test IP: 204.13.154.3)"), "Los Angeles DC-02"
        )
        self.assertEqual(normalize_location_name("New York (Test IP: 192.3.81.8)"), "New York")

    def test_parse_server_specs_extracts_multi_disk(self) -> None:
        specs = parse_server_specs(
            "\n".join(
                [
                    "Intel Xeon E3-1240 V3 - 4x 3.40 GHz (8 Threads, 3.80 GHz Turbo)",
                    "32 GB RAM",
                    "500 GB SSD (main drive)",
                    "2 TB SATA HDD (secondary drive)",
                    "30 TB Monthly Transfer",
                    "1Gbps Network Port",
                ]
            )
        )

        self.assertEqual(specs.memory, "32 GB RAM")
        self.assertEqual(specs.monthly_transfer, "30 TB Monthly Transfer")
        self.assertEqual(specs.public_network_port, "1Gbps Network Port")
        self.assertEqual(
            specs.disks,
            [
                DiskInfo(
                    raw="500 GB SSD (main drive)",
                    size_value=500.0,
                    size_unit="GB",
                    label="SSD (main drive)",
                ),
                DiskInfo(
                    raw="2 TB SATA HDD (secondary drive)",
                    size_value=2.0,
                    size_unit="TB",
                    label="SATA HDD (secondary drive)",
                ),
            ],
        )


class FixtureBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch()
        self.context = await self.browser.new_context(base_url="https://my.racknerd.com")
        self.page = await self.context.new_page()

    async def asyncTearDown(self) -> None:
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()

    async def test_extract_product_tasks_from_fixture_filters_monthly_cards(self) -> None:
        await self.page.set_content(read_fixture("store_catalog.html"))
        tasks = await extract_product_tasks_from_page(
            self.page,
            category_name="Black Friday 2025",
            category_url="https://my.racknerd.com/index.php?rp=/store/blackfriday2025",
        )

        self.assertEqual(len(tasks), 2)
        self.assertEqual(
            [task.store_title for task in tasks],
            ["1 GB KVM VPS (Black Friday 2025)", "1.5 GB Ryzen VPS"],
        )
        self.assertTrue(all(task.store_price_cycle == "Annually" for task in tasks))

    async def test_discover_target_category_urls_ignores_marketing_links(self) -> None:
        await self.page.set_content(read_fixture("store_index_categories.html"))
        category_urls = await discover_target_category_urls(
            self.page,
            "https://my.racknerd.com/index.php?rp=/store/blackfriday2025",
            ["KVM VPS", "AMD Ryzen Linux KVM VPS", "New Year Specials", "Black Friday 2025"],
        )

        self.assertEqual(
            category_urls,
            [
                "https://my.racknerd.com/index.php?rp=/store/kvm-vps",
                "https://my.racknerd.com/index.php?rp=/store/amd-ryzen-linux-kvm-vps",
                "https://my.racknerd.com/index.php?rp=/store/new-year-specials",
                "https://my.racknerd.com/index.php?rp=/store/blackfriday2025",
            ],
        )

    async def test_extract_server_info_from_confproduct_fixture(self) -> None:
        await self.page.set_content(read_fixture("confproduct_fixture.html"))
        task = ProductTask(
            category_name="AMD Ryzen Linux KVM VPS",
            category_url="https://my.racknerd.com/index.php?rp=/store/amd-ryzen-linux-kvm-vps",
            product_url="https://my.racknerd.com/cart.php?a=confproduct&i=1",
            store_title="1GB Ryzen VPS",
            store_price_cycle="Annually",
        )
        updated_at = datetime(2026, 3, 22, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

        server = await extract_server_info_from_page(self.page, task, updated_at)

        self.assertIsNotNone(server)
        assert server is not None
        self.assertEqual(server.billing_cycle_annually_usd, 32.55)
        self.assertEqual(server.model, "AMD Ryzen Linux KVM VPS - 1GB Ryzen VPS")
        self.assertEqual(
            server.normalized_locations, ["Los Angeles DC-02", "Los Angeles DC-03", "New York"]
        )
        self.assertEqual(server.specs.memory, "1 GB DDR4 RAM")
        self.assertEqual(server.specs.public_network_port, "1Gbps Public Network Port")


class StorageTests(unittest.TestCase):
    def test_save_snapshot_writes_latest_and_history(self) -> None:
        updated_at = datetime(2026, 3, 22, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        snapshot = SnapshotFile(
            updated_at=updated_at,
            source_categories=["Black Friday 2025"],
            item_count=1,
            items=[
                ServerInfo(
                    category_name="Black Friday 2025",
                    store_title="1 GB KVM VPS (Black Friday 2025)",
                    model="1 GB KVM VPS (Black Friday 2025)",
                    product_url="https://my.racknerd.com/index.php?rp=/store/blackfriday2025/1-gb-kvm-vps-black-friday-2025",
                    confproduct_url="https://my.racknerd.com/cart.php?a=confproduct&i=0",
                    store_price_cycle="Annually",
                    billing_cycle_annually_usd=10.6,
                    raw_locations=["New York (Test IP: 192.3.81.8)"],
                    normalized_locations=["New York"],
                    specs=ServerSpecs(memory="1 GB RAM"),
                    updated_at=updated_at,
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            saved = save_snapshot(snapshot, Path(tmp_dir))
            self.assertTrue(saved.latest_path.exists())
            self.assertTrue(saved.history_path.exists())
            self.assertIn("20260322-210000", saved.history_path.name)


@unittest.skipUnless(
    os.getenv("RUN_LIVE_RACKNERD_TESTS") == "1", "Live RackNerd smoke test disabled"
)
class LiveSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_snapshot_with_black_friday_category(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            snapshot = await run_snapshot(
                ScraperConfig(
                    category_urls=["https://my.racknerd.com/index.php?rp=/store/blackfriday2025"],
                    max_concurrency=1,
                    output_dir=Path(tmp_dir),
                )
            )
        self.assertGreater(snapshot.item_count, 0)
        first = snapshot.items[0]
        self.assertIsNotNone(first.billing_cycle_annually_usd)
        self.assertTrue(first.normalized_locations)
        self.assertIsNotNone(first.updated_at)
