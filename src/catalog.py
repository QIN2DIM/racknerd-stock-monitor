from __future__ import annotations

from typing import Final, Literal, get_args


RackNerdCategory = Literal[
    "Shared Hosting",
    "Reseller Hosting",
    "KVM VPS",
    "Hybrid Dedicated Servers",
    "Colocation",
    "Dedicated Servers",
    "High Bandwidth Unmetered Dedicated Servers",
    "AMD Ryzen/EPYC Dedicated Servers",
    "SEO Dedicated Servers",
    "Windows VPS with NVMe SSD",
    "AMD Ryzen Linux KVM VPS",
    "RackNerd Merchandise",
    "New Year Specials",
    "Black Friday 2025",
]

SubscribedRackNerdCategory = RackNerdCategory | Literal["seed"]

ALL_RACKNERD_CATEGORIES: Final[tuple[RackNerdCategory, ...]] = get_args(RackNerdCategory)

DEFAULT_SUBSCRIBED_CATEGORIES: Final[list[RackNerdCategory]] = [
    "KVM VPS",
    "AMD Ryzen Linux KVM VPS",
    "New Year Specials",
    "Black Friday 2025",
]
