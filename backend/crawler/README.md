# crawler — 공지 수집(스크래핑) 파이프라인

## 개요

`crawler` 는 외부 공지 사이트를 주기적으로 긁어 `notices.Notice` 로 저장한다. 대상 사이트는 코드가 아니라 설정(`config/sites.json`)으로 관리하고, 사이트마다 전용 스크래퍼가 목록을 표준 형태(`RawNotice`)로 반환하면 저장소(`repository`)가 Django 모델로 영속화한다. 정적 HTML 을 `httpx` + `BeautifulSoup`(lxml)로 파싱하며, 게시일 문자열은 사이트별 형식·상대표현까지 유연하게 파싱한다(`dateparse`). 외부 사이트 장애는 리포트(`CrawlReport.errors`)로 남겨 한 사이트 실패가 전체 수집을 멈추지 않게 한다(NFR-3). 프론트가 크롤러를 직접 부르지 않고, 크롤은 서버 내부 작업이며 프론트는 `notices` API 로 저장된 결과만 읽는다.

## 구성

| 파일 | 역할 |
| --- | --- |
| `config/sites.json` | 크롤 대상 사이트 목록(`id`·`name`·`url`·`scraper`·`category`·`enabled`)과 요청 기본값 |
| `config_loader.py` | `sites.json` → `CrawlerConfig`/`SiteConfig`/`Defaults` 로더 |
| `scrapers/` | 사이트별 스크래퍼 + `base.py`(파싱 헬퍼: 목록 행 날짜 추출·본문 추출·안전한 링크), `__init__.py`의 `REGISTRY` |
| `fetcher.py` | 공통 `httpx.Client`(User-Agent·타임아웃·리다이렉트) |
| `schemas.py` | `RawNotice`(스크래퍼 출력 표준형)·`CrawlReport`(pydantic) |
| `service.py` | `NoticeCrawlService` — 스크랩·저장 오케스트레이션(`crawl_site`/`crawl_all`/`crawl_recent`/`preview_site`) |
| `repository.py` | `DjangoNoticeRepository` — `RawNotice` → `NoticeSource`/`Notice` 저장, 게시일 파싱, (옵션) 순진한 매칭 |
| `matcher.py` | `match_notice_to_subscribers` — 관심 키워드 부분일치로 임시 `InboxNotice` 생성(AI 미실행 시 폴백) |
| `dateparse.py` | 게시일/상대표현 유연 파서 |
| `management/commands/` | `crawl_notices`(단발 크롤), `run_scheduler`(주기 루프) |

## 흐름 · 사용법

저장 흐름: `외부 사이트 → scrapers → RawNotice → sources.NoticeSource → notices.Notice`. 새 `Notice` 저장 시(매칭이 켜져 있으면) `matcher` 가 임시 `InboxNotice` 를 남기지만, 이는 AI 미실행 환경의 독립 폴백일 뿐이고 파이프라인의 실제 선별은 AI(`ai.service`)가 담당한다.

```bash
# DB 저장 없이 미리보기
python manage.py crawl_notices --source snu_cse_notice --preview --limit 3

# 실제 저장(순진한 키워드 매칭 끔 — inbox 편입은 AI 선별에 위임)
python manage.py crawl_notices --source snu_cse_notice --no-match

# --source 생략 시 enabled 사이트 전체를 순서대로 크롤

# 주기 스케줄러(크롤 → 보강 → 선별 → 발송)
python manage.py run_scheduler --once                 # 한 틱만
python manage.py run_scheduler --interval-minutes 30  # 30분 루프
```

`run_scheduler` 는 매 틱마다 due 사이트(`crawl_interval_minutes` 경과 또는 미크롤)만 크롤하고, 새로 저장된 공지를 AI 보강한 뒤 `classify_notices` → `dispatch_alerts` 를 부른다.

현재 카탈로그(전부 정적 HTTP): `snu_cse_notice`, `snu_cba_notice`, `saramin_hot100`, `naver_recruit`, `jobkorea_ai`, `naver_cafe_notice`, `thedream_scholarships`, `thedream_activities`, `thedream_contests`, `interpark_concert`.

## 유의사항

- `--source` 없이 실행하면 여러 외부 사이트에 연속 요청하므로, 개별 확인은 `--source` 로 한 사이트씩 하는 것을 권장한다. 사이트 사이에는 예의상 요청 지연(`request_delay_seconds`)을 둔다(NFR-5).
- 파이프라인 표준 경로는 **순진한 매칭을 끄고(`--no-match`) AI 선별을 유일한 선별기로** 둔다. `run_scheduler`·sync 는 항상 `match_inbox=False` 로 크롤한다. `matcher.py` 는 AI 없이 크롤만 돌릴 때의 폴백으로 남겨둔 것이다.
- 게시일 파싱에 실패하면 `published_at` 은 `null` 로 저장된다. 사이트 구조가 바뀌면 해당 스크래퍼의 파싱 로직을 다시 확인해야 한다.
- `fetcher.py` 는 개발 환경 편의를 위해 `verify=False`(SSL 검증 생략)·`trust_env=False` 로 열려 있다. 운영 배포 전에는 설정으로 분리·재검토가 필요하다.
- 동일성은 `(source_id, url)` 유니크로 판정한다 — 같은 사이트의 같은 URL 은 재크롤해도 중복으로 처리된다.
