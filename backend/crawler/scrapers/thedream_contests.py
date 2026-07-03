from __future__ import annotations

from typing import Iterable

from ..schemas import RawNotice
from .base import ScrapeContext
from .thedream_common import TheDreamFeed, make_contest_notice, scrape_thedream_feed


def scrape(ctx: ScrapeContext) -> Iterable[RawNotice]:
    return scrape_thedream_feed(
        ctx,
        TheDreamFeed(
            table="activities",
            order="created_at.desc",
            type_filter="contest",
            mapper=make_contest_notice,
        ),
    )
