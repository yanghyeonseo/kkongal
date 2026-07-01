from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "sites.json"


@dataclass(frozen=True)
class SiteConfig:
    id: str
    name: str
    url: str
    scraper: str
    category: str
    enabled: bool
    render: str


@dataclass(frozen=True)
class Defaults:
    user_agent: str
    request_delay_seconds: int
    request_timeout_seconds: int
    max_items_per_run: int


@dataclass(frozen=True)
class CrawlerConfig:
    sites: tuple[SiteConfig, ...]
    defaults: Defaults

    def site(self, site_id: str) -> SiteConfig:
        for s in self.sites:
            if s.id == site_id:
                return s
        raise KeyError(f"unknown site: {site_id}")

    def enabled_sites(self) -> Iterable[SiteConfig]:
        return (s for s in self.sites if s.enabled)


def load_config(path: Path | str | None = None) -> CrawlerConfig:
    target = Path(path) if path else CONFIG_PATH
    raw = json.loads(target.read_text(encoding="utf-8"))
    sites = tuple(
        SiteConfig(
            id=s["id"],
            name=s["name"],
            url=s["url"],
            scraper=s["scraper"],
            category=s["category"],
            enabled=bool(s.get("enabled", True)),
            render=s.get("render", "http"),
        )
        for s in raw["sites"]
    )
    d = raw.get("defaults", {})
    defaults = Defaults(
        user_agent=d.get("user_agent", "Mozilla/5.0"),
        request_delay_seconds=int(d.get("request_delay_seconds", 5)),
        request_timeout_seconds=int(d.get("request_timeout_seconds", 20)),
        max_items_per_run=int(d.get("max_items_per_run", 50)),
    )
    return CrawlerConfig(sites=sites, defaults=defaults)
