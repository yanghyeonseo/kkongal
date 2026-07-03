"""크롤러 단위테스트 — 네트워크 없음.

날짜 추출은 실제 사이트 HTML 구조를 본뜬 fixture 문자열을 스크래퍼의 ``parse_html``
(또는 페이로드 파서)에 먹여 검증한다. 7일/20건 선별 로직은 주입한 가짜 스크래퍼로
검증한다. 실제 fetch/LLM/이메일은 일절 호출하지 않는다.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from crawler.config_loader import load_config
from crawler.dateparse import parse_flexible, parse_relative_korean, to_naive
from crawler.repository import parse_notice_datetime
from crawler.schemas import RawNotice
from crawler.scrapers import saramin_hot100, snu_cba_notice, snu_cse_notice
from crawler.service import NoticeCrawlService

CONFIG = load_config()


def _raw(index: int, posted_at):
    return RawNotice(
        source_id="snu_cse_notice",
        title=f"공지 {index}",
        url=f"https://example.com/{index}",
        posted_at=posted_at,
    )


# --- 날짜 추출: 사이트 목록 HTML fixture ------------------------------------

SNU_CSE_HTML = """
<ul class="board-list">
  <li class="flex odd:bg-neutral-50">
    <span><svg viewBox="0 0 48 48"></svg></span>
    <a href="/ko/community/notice/25248">
      <span>2026 상반기 산학장학생 모집 (~7/15)</span>
    </a>
    <span>2026/7/01</span>
  </li>
  <li class="flex">
    <a href="/ko/community/notice/25242"><span>두 번째 공지</span></a>
    <span>2026/6/30</span>
  </li>
</ul>
"""

SNU_CBA_HTML = """
<table><tbody>
  <tr class="noti">
    <td class="text-center">공지</td>
    <td class="text-center">일반</td>
    <td class="title noti-tit">
      <a href="/newsroom/notice?md=v&amp;bbsidx=26166"><span>후기 학위수여식 안내</span></a>
    </td>
    <td class="text-center FS12">2026-07-02</td>
    <td class="text-center">70</td>
  </tr>
  <tr>
    <td class="text-center">1</td>
    <td class="text-center">일반</td>
    <td class="title"><a href="/newsroom/notice?md=v&amp;bbsidx=26150"><span>수강반 제한 안내</span></a></td>
    <td class="text-center">2026-07-01</td>
    <td class="text-center">42</td>
  </tr>
</tbody></table>
"""

SARAMIN_HTML = """
<div class="list_item" id="rec-1">
  <div class="col company_nm"><span class="str_tit">테스트회사</span></div>
  <div class="col notification_info">
    <div class="job_tit">
      <a class="str_tit" href="/zf_user/jobs/relay/view?rec_idx=123"><span>백엔드 개발자 채용</span></a>
    </div>
  </div>
  <div class="col support_info">
    <p class="support_detail">
      <span class="date">D-7</span>
      <span class="deadlines">6일 전 등록</span>
    </p>
  </div>
</div>
"""


class DateExtractionTests(SimpleTestCase):
    def test_snu_cse_extracts_slash_date_not_title_date(self):
        site = CONFIG.site("snu_cse_notice")
        notices = snu_cse_notice.parse_html(SNU_CSE_HTML, site, CONFIG.defaults)
        self.assertEqual(len(notices), 2)
        # 제목에 "(~7/15)" 가 섞여 있어도 날짜 셀("2026/7/01")만 뽑아야 한다.
        self.assertEqual(notices[0].posted_at, "2026/7/01")
        self.assertEqual(notices[1].posted_at, "2026/6/30")
        # 그리고 그 문자열은 실제 datetime 으로 파싱된다.
        self.assertEqual(parse_flexible(notices[0].posted_at).date(), datetime(2026, 7, 1).date())

    def test_snu_cba_extracts_iso_td_date(self):
        site = CONFIG.site("snu_cba_notice")
        notices = snu_cba_notice.parse_html(SNU_CBA_HTML, site, CONFIG.defaults)
        self.assertEqual(len(notices), 2)
        self.assertEqual(notices[0].posted_at, "2026-07-02")
        self.assertEqual(notices[1].posted_at, "2026-07-01")

    def test_saramin_extracts_relative_registration_time(self):
        site = CONFIG.site("saramin_hot100")
        notices = saramin_hot100.parse_html(SARAMIN_HTML, site, CONFIG.defaults)
        self.assertEqual(len(notices), 1)
        # ".date"(마감 D-7)가 아니라 ".deadlines"(상대 게시시각)를 뽑아야 한다.
        self.assertEqual(notices[0].posted_at, "6일 전 등록")
        self.assertIn("테스트회사", notices[0].title)


class DateParseTests(SimpleTestCase):
    def test_relative_korean_units(self):
        now = datetime(2026, 7, 3, 12, 0, 0)
        self.assertEqual(parse_relative_korean("6일 전 등록", now).date(), datetime(2026, 6, 27).date())
        self.assertEqual(parse_relative_korean("2주 전", now).date(), datetime(2026, 6, 19).date())
        self.assertEqual(parse_relative_korean("18시간 전 수정", now), now - timedelta(hours=18))
        self.assertEqual(parse_relative_korean("30분 전", now), now - timedelta(minutes=30))
        self.assertEqual(parse_relative_korean("어제", now).date(), datetime(2026, 7, 2).date())
        self.assertEqual(parse_relative_korean("그저께", now).date(), datetime(2026, 7, 1).date())
        self.assertEqual(parse_relative_korean("방금 전", now), now)

    def test_relative_korean_ignores_absolute(self):
        self.assertIsNone(parse_relative_korean("2026-07-02"))
        self.assertIsNone(parse_relative_korean(""))

    def test_flexible_absolute_formats(self):
        self.assertEqual(parse_flexible("2026/7/01").date(), datetime(2026, 7, 1).date())
        self.assertEqual(parse_flexible("2026-07-02").date(), datetime(2026, 7, 2).date())
        self.assertEqual(parse_flexible("2026.06.23 12:00:00"), datetime(2026, 6, 23, 12, 0, 0))
        iso = parse_flexible("2026-07-01T08:54:16+00:00")
        self.assertIsNotNone(iso.tzinfo)
        self.assertIsNone(parse_flexible(None))
        self.assertIsNone(parse_flexible("설명 없음"))

    def test_to_naive_strips_tzinfo(self):
        aware = parse_flexible("2026-07-01T08:54:16+00:00")
        self.assertIsNone(to_naive(aware).tzinfo)
        self.assertIsNone(to_naive(None))

    def test_parse_notice_datetime_relative_is_aware(self):
        result = parse_notice_datetime("6일 전 등록")
        self.assertIsNotNone(result)
        self.assertFalse(timezone.is_naive(result))
        expected = timezone.now() - timedelta(days=6)
        self.assertLess(abs((result - expected).total_seconds()), 120)

    def test_parse_notice_datetime_passthrough_and_none(self):
        self.assertEqual(parse_notice_datetime("2026-07-02").date(), datetime(2026, 7, 2).date())
        self.assertIsNone(parse_notice_datetime(None))
        self.assertIsNone(parse_notice_datetime(""))


class SelectRecentTests(SimpleTestCase):
    def test_caps_at_limit_most_recent_first(self):
        items = [_raw(i, "방금 전") for i in range(25)]
        result = NoticeCrawlService._select_recent(items, days=7, limit=20)
        self.assertEqual(len(result), 20)

    def test_filters_outside_window(self):
        items = [
            _raw(0, "1일 전"),
            _raw(1, "3일 전"),
            _raw(2, "10일 전"),
            _raw(3, "20일 전"),
        ]
        result = NoticeCrawlService._select_recent(items, days=7, limit=20)
        self.assertEqual([n.title for n in result], ["공지 0", "공지 1"])

    def test_missing_dates_fall_back_to_newest_scrape_order(self):
        items = [_raw(i, None) for i in range(25)]
        result = NoticeCrawlService._select_recent(items, days=7, limit=20)
        self.assertEqual(len(result), 20)
        self.assertEqual(result[0].title, "공지 0")
        self.assertEqual(result[19].title, "공지 19")

    def test_all_old_falls_back_to_newest_dated(self):
        items = [_raw(0, "20일 전"), _raw(1, "10일 전"), _raw(2, "30일 전")]
        result = NoticeCrawlService._select_recent(items, days=7, limit=20)
        # 윈도우 안이 없으니 날짜 있는 것 중 최신순으로 폴백(10일 전 < 20일 전 < 30일 전).
        self.assertEqual([n.title for n in result], ["공지 1", "공지 0", "공지 2"])

    def test_mixed_dated_within_then_undated_topup(self):
        items = [_raw(0, "1일 전"), _raw(1, None), _raw(2, "2일 전"), _raw(3, None)]
        result = NoticeCrawlService._select_recent(items, days=7, limit=20)
        self.assertEqual([n.title for n in result], ["공지 0", "공지 2", "공지 1", "공지 3"])


class CrawlRecentWiringTests(SimpleTestCase):
    def test_crawl_recent_uses_scraper_and_applies_selection(self):
        # 가짜 스크래퍼를 주입 — 네트워크 fetch 없음.
        def fake_scraper(ctx):
            return [_raw(i, "방금 전") for i in range(25)]

        service = NoticeCrawlService(
            config=CONFIG,
            repository=None,
            scraper_resolver=lambda name: fake_scraper,
        )
        report = service.crawl_recent("snu_cse_notice", days=7, limit=20)
        # crawl_recent 은 CrawlReport 를 돌려준다: 25건 중 선택 20건(fetched),
        # repository=None 이라 저장은 0(inserted), 스크랩 오류 없음.
        self.assertEqual(report.fetched, 20)
        self.assertEqual(report.inserted, 0)
        self.assertEqual(report.errors, [])
