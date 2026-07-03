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
| `POST /api/sources/<id>/sync/` | 온디맨드 동기화 큐 등록 → 즉시 `{status:"started"}` 반환(아래 참고) |
| `GET /api/sources/sync/status/` | 진행 중/완료 동기화 작업 상태(사이트별 폴링용) |

**온디맨드 동기화(`SourceSyncView` · `sync_jobs.py`)** — 사이드바/등록 모달의 "동기화" 버튼이 호출한다. LLM 요청 스로틀(요청 간 ~4.5s) 때문에 크롤·선별을 요청 안에서 처리하면 응답이 오래 걸리므로, 이 뷰는 검증(인증·구독·미지원 사이트 400·30초 재크롤 제한)만 동기로 하고 실제 작업은 **큐에 등록한 뒤 곧바로 `{status:"started"}` 로 반환**한다. 단일 순차 백그라운드 워커가 큐를 하나씩 비우며 사이트별로 최근 7일·최대 20건 스크랩 → 신규 공지 보강(`ai.enrich`) → 가장 최근 10건을 **요청 사용자에 대해서만** 선별(`ai.service.classify_notices_for_user`) → 신규 추천분(`is_recommended=true`) 알림 발송(`alert.service.dispatch_pending`)까지 처리하고, 결과(`running`/`done`/`failed` + 담긴 추천 수 + 메시지)를 캐시에 남긴다. 프론트는 `GET /api/sources/sync/status/` 를 폴링해 **사이트가 하나씩 완료되는 대로** 토스트·목록 갱신을 보여준다. 자동 수집 미지원 사이트는 400(큐 등록 없음), 라이브 사이트 장애는 워커 단계에서 `failed` 로 격리된다.

## 유의사항

- `favicon_url` 은 백엔드가 계산해 저장하는 **응답 전용** 필드다. `name` 만 `PATCH /api/sources/<id>/` 로 편집할 수 있고, 편집·동기화 모두 **구독자 본인만** 가능하다(아니면 403).
- 표시명·파비콘 계산은 사이트를 직접 받아오지 않으므로 등록이 항상 즉시 성공한다. 반대로 실제 공지 수집은 카탈로그(`sites.json`)에 URL 이 있는 사이트만 가능하다 — 카탈로그에 없는 임의 URL 은 구독은 되지만 sync 시 "자동 수집 미지원(400)" 이다.
- 동기화의 LLM 비용은 사용자당·요청당 상한(최근 10건)으로 억제한다. 전체 구독자 대상 선별은 sync 가 아니라 파이프라인/스케줄러(`crawler.run_scheduler` → `classify_notices`)가 담당한다.
- 동기화 워커와 상태 캐시는 **프로세스 지역**이다(기본 LocMemCache). 개발 `runserver`(단일 프로세스·멀티스레드)에서는 워커·폴링이 같은 프로세스라 문제없지만, gunicorn 등 멀티프로세스 배포에서는 공유 캐시(Redis 등)가 필요하다. LLM 요청 스로틀(`LLM_MIN_REQUEST_INTERVAL_SECONDS`)도 프로세스별이라 실효 RPM 이 워커 수만큼 커지므로, 동기화/스케줄러 경로는 단일 워커를 권장한다.
- `crawled_at` 은 크롤 저장 시점에 갱신되며(→ `crawler/repository.py`), 스케줄러의 "due 사이트" 판정(`crawl_interval_minutes` 기준)에 쓰인다.
