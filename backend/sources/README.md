# sources — 공지 출처(사이트)와 구독

## 개요

`sources` 는 공지가 나오는 **출처 사이트(`NoticeSource`)** 를 전역으로 관리하고, 사용자가 그 사이트를 **구독(`SourceSubscription`)** 하도록 연결한다. 사이트 등록은 URL 만 받아 빠르게 처리한다 — 표시명과 파비콘은 네트워크 왕복 없이 URL 만으로 계산하므로(파비콘은 Google s2 서비스 URL, 표시명은 카탈로그 이름 또는 도메인) 등록이 느려지거나 실패하지 않는다. 자동 수집이 지원되는 사이트는 `crawler/config/sites.json` 카탈로그로 노출되며, 사용자는 카탈로그에서 고르거나 임의 URL 을 직접 등록할 수 있다. 또한 사이트별 **온디맨드 동기화(sync)** 로 즉시 크롤·보강·선별을 돌려 대시보드를 채운다.

## 구성

| 파일 | 역할 |
| --- | --- |
| `models.py` | `NoticeSource`(`name`·`url`(unique)·`favicon_url`·`crawl_interval_minutes`·`crawled_at`·`created_at`), `SourceSubscription`(`user_id`×`source_id` 유니크) |
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
| `GET /api/sources/catalog/` | 자동 수집 지원 사이트 카탈로그(인증 시 구독 여부·source_id 포함) |
| `PATCH /api/sources/<id>/` | 구독한 사이트의 표시명(name) 편집 |
| `POST /api/sources/<id>/sync/` | 온디맨드 동기화(아래 참고) |

**온디맨드 동기화(`SourceSyncView`)** — 사이드바/등록 모달의 "동기화" 버튼이 호출한다. 구독한 사이트에서 최근 7일 이내 공지를 최대 20건 스크랩하고, 새로 저장된 공지는 공지당 1회 보강(`ai.enrich`)한 뒤, 가장 최근 10건을 **요청 사용자에 대해서만** AI 선별(`ai.service.classify_notices_for_user`)해 개인 피드에 담는다. 선별 후 요청 사용자의 신규 추천 공지(`is_recommended=true`)에 대해 비차단, best-effort 로 알림을 발송한다(`alert.service.dispatch_pending`). 최근 30초 내 크롤 이력이 있으면 재크롤을 생략하고 기존 공지만 재선별하며(사이트 부하·비용 보호), 자동 수집 미지원 사이트는 400, 라이브 사이트 장애 시에도 500 대신 `crawled=false` + 안내 메시지를 담아 200 으로 응답한다.

## 유의사항

- `favicon_url` 은 백엔드가 계산해 저장하는 **응답 전용** 필드다. `name` 만 `PATCH /api/sources/<id>/` 로 편집할 수 있고, 편집·동기화 모두 **구독자 본인만** 가능하다(아니면 403).
- 표시명·파비콘 계산은 사이트를 직접 받아오지 않으므로 등록이 항상 즉시 성공한다. 반대로 실제 공지 수집은 카탈로그(`sites.json`)에 URL 이 있는 사이트만 가능하다 — 카탈로그에 없는 임의 URL 은 구독은 되지만 sync 시 "자동 수집 미지원(400)" 이다.
- 동기화의 LLM 비용은 사용자당·요청당 상한(최근 10건)으로 억제한다. 전체 구독자 대상 선별은 sync 가 아니라 파이프라인/스케줄러(`crawler.run_scheduler` → `classify_notices`)가 담당한다.
- `crawled_at` 은 크롤 저장 시점에 갱신되며(→ `crawler/repository.py`), 스케줄러의 "due 사이트" 판정(`crawl_interval_minutes` 기준)에 쓰인다.
