# notices — 공지 원본과 사용자별 공지함(inbox)

## 개요

`notices` 는 두 개의 축을 관리한다. 하나는 크롤러가 수집한 **공지 원본(`Notice`)** 으로, 출처·URL·제목·본문에 더해 AI 보강 산출물(3문장 요약·정리된 markdown·마감일)을 담는다. 다른 하나는 AI 선별 결과인 **사용자별 공지함(`InboxNotice`)** 으로, `(사용자, 공지)` 쌍마다 관련도·매칭 키워드·선별 사유·읽음/저장 상태·알림 발송 시각을 갖는다. 대시보드가 읽는 개인 피드가 바로 이 inbox 이며, 프론트 AI 상태 배너를 위한 가벼운 상태 조회 엔드포인트도 이 앱이 노출한다.

## 구성

| 파일 | 역할 |
| --- | --- |
| `models.py` | `Notice`(`source_id`·`url`·`hash`·`title`·`content`·`summary`·`content_markdown`·`publisher`·`published_at`·`deadline_at`·`updated_at`·`created_at`, `(source_id, url)` 유니크), `InboxNotice`(`user_id`·`notice_id`·`relevance_score`·`matched_keywords`·`reason`·`is_read`·`is_saved`·`notified_at`·`created_at`, `(user_id, notice_id)` 유니크) |
| `serializers.py` | `NoticeSerializer`(중첩 source 포함), `InboxNoticeSerializer`(중첩 notice + `deadline_at` 노출), `InboxNoticeSaveSerializer`, `InboxNoticeReadSerializer` |
| `views.py` | inbox 목록/상세/저장/읽음 뷰 + `AiStatusView` |
| `urls.py` | `urlpatterns`(`/api/notices/inbox/...`), `ai_urlpatterns`(`/api/ai/status/`) |
| `management/commands/run_pipeline.py` | 전체 파이프라인 단일 진입점: (크롤) → 보강 → 선별 → 발송 |

## 흐름 · 사용법

`Notice` 는 크롤러(`crawler.repository`)가 저장하고 AI 보강(`ai.enrich`)이 요약/markdown/마감일을 채운다. `InboxNotice` 는 AI 선별(`ai.service`)이 임계값 이상일 때 생성/갱신한다. 대시보드는 아래 inbox API 로 개인 피드를 조회하고 저장/읽음 상태를 바꾼다.

| 메서드 · 경로 | 설명 |
| --- | --- |
| `GET /api/notices/inbox/` | 내 공지함 목록(게시일·최신순). `?saved=true\|false` 로 저장 필터 |
| `GET /api/notices/inbox/<id>/` | 공지함 항목 상세 |
| `PATCH /api/notices/inbox/<id>/save/` | 저장/저장 해제(`{"is_saved": bool}`) |
| `PATCH /api/notices/inbox/<id>/read/` | 읽음/안읽음(`{"is_read": bool}`, 기본 true — 열면 읽음 처리) |
| `GET /api/ai/status/` | AI 가용 상태(`{degraded, reason, message}`) — 프론트 배너용, 공개 |

**전체 파이프라인 명령**:

```bash
python manage.py run_pipeline          # 저장된 공지로 보강 → 선별 → 발송(크롤 없음, 빠름)
python manage.py run_pipeline --crawl  # 라이브 크롤부터 끝까지
```

`run_pipeline` 은 `crawl_notices`(선택) → 보강(`enrich_notices`) → `classify_notices` → `dispatch_alerts` 를 순서대로 부르며, 각 단계는 격리되어 한 단계 실패가 다음을 막지 않는다. `--no-enrich`/`--no-classify`/`--no-dispatch`·`--source`·`--limit`·`--dry-run` 옵션을 지원한다.

## 유의사항

- **알림 발송의 중복 방지 기준은 `InboxNotice.notified_at`** 이다(null=미발송). 이 필드는 알림 계층(`alert`)만 갱신하며, AI 선별(`ai.service`)은 upsert 시에도 절대 건드리지 않는다.
- `matched_keywords` 는 계약상 콤마-join 문자열로 저장한다. 소비 측(프론트·알림 발송)은 JSON 배열 문자열도 방어적으로 파싱한다.
- 마감 상태(임박/지남)는 서버가 아니라 프론트가 `deadline_at` 으로 계산한다(0~7일=임박, 음수=지남).
- AI 상태(`AiStatusView`)는 민감정보가 없어 공개(`AllowAny`)다. 나머지 inbox 뷰는 모두 로그인 사용자 본인 데이터로 한정된다.
- 크롤러의 순진한 키워드 매처가 남기는 플레이스홀더 inbox 행(`reason == "Keyword match"`, score 1.0)은 AI 선별이 실제 점수/사유로 덮어쓴다(→ `ai/service.py`).
