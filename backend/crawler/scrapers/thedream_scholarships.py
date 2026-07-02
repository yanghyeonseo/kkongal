from __future__ import annotations

from typing import Iterable

from ..schemas import RawNotice
from .base import ScrapeContext
from .thedream_common import TheDreamFeed, make_scholarship_notice, scrape_thedream_feed


def scrape(ctx: ScrapeContext) -> Iterable[RawNotice]:
    return scrape_thedream_feed(
        ctx,
        TheDreamFeed(
            table="scholarships",
            order="created_at.desc",
            mapper=make_scholarship_notice,
        ),
    )
