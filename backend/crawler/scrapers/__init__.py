from __future__ import annotations

from . import (
    interpark_concert,
    jobkorea_ai,
    naver_cafe_notice,
    naver_recruit,
    saramin_hot100,
    snu_cba_notice,
    snu_cse_notice,
    thedream_activities,
    thedream_contests,
    thedream_scholarships,
)
from .base import ScrapeContext, Scraper

REGISTRY: dict[str, Scraper] = {
    "snu_cse_notice": snu_cse_notice.scrape,
    "snu_cba_notice": snu_cba_notice.scrape,
    "saramin_hot100": saramin_hot100.scrape,
    "naver_recruit": naver_recruit.scrape,
    "jobkorea_ai": jobkorea_ai.scrape,
    "naver_cafe_notice": naver_cafe_notice.scrape,
    "thedream_scholarships": thedream_scholarships.scrape,
    "thedream_activities": thedream_activities.scrape,
    "thedream_contests": thedream_contests.scrape,
    "interpark_concert": interpark_concert.scrape,
}


def get(name: str) -> Scraper:
    if name not in REGISTRY:
        raise KeyError(f"unknown scraper: {name}")
    return REGISTRY[name]


__all__ = [
    "REGISTRY",
    "ScrapeContext",
    "Scraper",
    "get",
    "snu_cse_notice",
    "snu_cba_notice",
    "saramin_hot100",
    "naver_recruit",
    "jobkorea_ai",
    "naver_cafe_notice",
    "thedream_scholarships",
    "thedream_activities",
    "thedream_contests",
    "interpark_concert",
]
