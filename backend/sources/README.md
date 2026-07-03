# sources — 공지 출처(사이트)와 구독

## 개요

`sources` 는 공지가 나오는 **출처 사이트(`NoticeSource`)** 를 전역으로 관리하고, 사용자가 그 사이트를 **구독(`SourceSubscription`)** 하도록 연결한다. 사이트 등록은 URL 만 받아 빠르게 처리한다 — 표시명과 파비콘은 네트워크 왕복 없이 URL 만으로 계산하므로(파비콘은 Google s2 서비스 URL, 표시명은 카탈로그 이름 또는 도메인) 등록이 느려지거나 실패하지 않는다.

**URL 정규화 · 레시피 공유(스케일링).** 등록 시 URL 을 정규화(`url_normalize.py`)해 `normalized_url` 키로 dedup 한다 — 스킴·`www.`·끝 슬래시·추적 파라미터(utm 등)·쿼리 순서·프래그먼트 차이를 흡수해, 표기만 다른 **같은 게시판이 하나의 `NoticeSource` 로 합쳐진다**. 그래서 어떤 사용자의 첫 크롤로 학습된 크롤 레시피(`crawler.generic` 의 `scraper_kind`·`extraction_profile`·`render`)를 다음 구독자가 그대로 재사용한다 — 사용자가 늘수록 이미 확정된 사이트가 많아져 자연히 스케일된다.

**카탈로그 · AI 자동 분류.** 자동 수집 대상은 `crawler/config/sites.json` 내장 카탈로그 + **크롤 레시피가 확정된 사용자 등록 커스텀 사이트**로, 사용자는 카탈로그에서 고르거나 임의 URL 을 직접 등록할 수 있다(카탈로그에 없는 사이트는 `crawler.generic` 파이프라인이 자동 수집). 커스텀 사이트는 첫 성공 크롤 시 AI(`ai_naming.py`)가 사이트 이름·카테고리를 채워 다른 사용자도 쉽게 발견·구독한다. 또한 사이트별 **온디맨드 동기화(sync)** 로 즉시 크롤·보강·선별을 돌려 대시보드를 채운다.

## 구성

| 파일 | 역할 |
| --- | --- |
| `models.py` | `NoticeSource`(`name`·`url`(unique)·`normalized_url`(unique, dedup 키)·`category`·`ai_named`·`favicon_url`·크롤 레시피 필드 `scraper_kind`·`extraction_profile`·`render`·`last_extract_ok_at`·`crawl_interval_minutes`·`crawled_at`·`created_at`; 클래스메서드 `resolve()` 로 정규화 dedup 생성), `SourceSubscription`(`user_id`×`source_id` 유니크) |
| `url_normalize.py` | `normalize_url(url)` — 스킴/`www.`/끝 슬래시/추적 파라미터/쿼리 순서/프래그먼트를 정규화한 dedup 키. 의미 있는 쿼리(menu·board id 등)는 보존 |
| `ai_naming.py` | `autofill_source_metadata(source)` — 첫 크롤 확정 시 최근 공지 제목으로 AI 가 사이트 이름·카테고리를 1회 채움(LLM 미가용/편집된 이름은 건드리지 않음) |
| `naming.py` | `favicon_url_for`(Google s2 파비콘 URL), `friendly_name_for`(카탈로그 이름 또는 도메인 기반 표시명) — 둘 다 네트워크 없이 URL 만으로 계산 |
| `serializers.py` | `NoticeSourceSerializer`, `NoticeSourceNameUpdateSerializer`(표시명 편집), `SourceSubscriptionSerializer`(중첩 source 포함), `SourceSubscriptionCreateSerializer`(url 입력) |
| `views.py` | 구독 목록/등록/삭제, 카탈로그, 표시명 편집, 온디맨드 동기화 뷰 |
| `urls.py` | `urlpatterns`(`/api/subscriptions/`), `sources_urlpatterns`(`/api/sources/` — 카탈로그·동기화·표시명 편집) |

## 흐름 · 사용법

사이트 등록(`POST /api/subscriptions/`)은 URL 로 전역 `NoticeSource` 를 `get_or_create` 하고 표시명·파비콘을 채운 뒤 요청 사용자의 구독을 연결한다. 대시보드는 구독 목록을 읽어 사이드바를 그린다.

| 메서드 · 경로 | 설명 |
| --- | --- |
| `GET /api/subscriptions/` | 내가 구독한 사이트 목록(중첩 source 포함) |
| `POST /api/subscriptions/` | URL 로 사이트 구독(전역 source 재사용) |
| `DELETE /api/subscriptions/<id>/` | 구독 해제 |
| `GET /api/sources/catalog/` | 내장 + 레시피 확정 커스텀 사이트 카탈로그(`custom` 플래그·category 포함, 인증 시 구독 여부·source_id) |
| `PATCH /api/sources/<id>/` | 구독한 사이트의 표시명(name) 편집 |
| `POST /api/sources/<id>/sync/` | 온디맨드 동기화 큐 등록 → 즉시 `{status:"started"}` 반환(아래 참고) |
| `GET /api/sources/sync/status/` | 진행 중/완료 동기화 작업 상태(사이트별 폴링용) |

**온디맨드 동기화(`SourceSyncView` · `sync_jobs.py`)** — 사이드바/등록 모달의 "동기화" 버튼이 호출한다. LLM 요청 스로틀(요청 간 ~4.5s) 때문에 크롤·선별을 요청 안에서 처리하면 응답이 오래 걸리므로, 이 뷰는 검증(인증·구독·30초 재크롤 제한)만 동기로 하고 실제 작업은 **큐에 등록한 뒤 곧바로 `{status:"started"}` 로 반환**한다. 단일 순차 백그라운드 워커가 큐를 하나씩 비우며 사이트별로 최근 7일·최대 20건 스크랩(내장 카탈로그면 전용 손파서, 그 외엔 `crawler.generic` 계단식) → 신규 공지 보강(`ai.enrich`) → 첫 크롤 확정 시 AI 사이트 이름·카테고리 자동채움(`ai_naming`) → 가장 최근 10건을 **요청 사용자에 대해서만** 선별(`ai.service.classify_notices_for_user`) → 신규 추천분(`is_recommended=true`) 알림 발송(`alert.service.dispatch_pending`)까지 처리하고, 결과(`running`/`done`/`failed` + 담긴 추천 수 + 메시지)를 캐시에 남긴다. 프론트는 `GET /api/sources/sync/status/` 를 폴링해 **사이트가 하나씩 완료되는 대로** 토스트·목록 갱신을 보여준다. 임의 사이트도 generic 파이프라인으로 자동 수집하며(별도 미지원 400 없음), 라이브 사이트 장애는 워커 단계에서 `failed` 로 격리된다.

## 유의사항

- `favicon_url` 은 백엔드가 계산해 저장하는 **응답 전용** 필드다. `name` 만 `PATCH /api/sources/<id>/` 로 편집할 수 있고, 편집·동기화 모두 **구독자 본인만** 가능하다(아니면 403).
- 표시명·파비콘 계산은 사이트를 직접 받아오지 않으므로 등록이 항상 즉시 성공한다. 실제 공지 수집은 카탈로그(`sites.json`)에 있으면 전용 손파서로, 없으면 `crawler.generic` 계단식(rss→heuristic→json_api→llm)으로 **임의 사이트도 자동 시도**한다(더는 "미지원 400" 없음). generic 은 서버가 임의 URL 을 직접 fetch 하므로 SSRF 가드(사설/메타데이터 대역 차단)가 걸려 있다.
- `normalized_url` 은 unique 이며 `NoticeSource.save()` 가 비어 있으면 자동으로 채운다 — 직접 `create()` 든 `resolve()` 든 항상 dedup 키가 보장된다. 같은 게시판을 가리키는 여러 표기의 URL 은 하나의 소스로 합쳐져 크롤 레시피를 공유한다.
- 동기화의 LLM 비용은 사용자당·요청당 상한(최근 10건)으로 억제한다. 전체 구독자 대상 선별은 sync 가 아니라 파이프라인/스케줄러(`crawler.run_scheduler` → `classify_notices`)가 담당한다.
- 동기화 워커와 상태 캐시는 **프로세스 지역**이다(기본 LocMemCache). 개발 `runserver`(단일 프로세스·멀티스레드)에서는 워커·폴링이 같은 프로세스라 문제없지만, gunicorn 등 멀티프로세스 배포에서는 공유 캐시(Redis 등)가 필요하다. LLM 요청 스로틀(`LLM_MIN_REQUEST_INTERVAL_SECONDS`)도 프로세스별이라 실효 RPM 이 워커 수만큼 커지므로, 동기화/스케줄러 경로는 단일 워커를 권장한다.
- `crawled_at` 은 크롤 저장 시점에 갱신되며(→ `crawler/repository.py`), 스케줄러의 "due 사이트" 판정(`crawl_interval_minutes` 기준)에 쓰인다.
