# ai — LLM 기반 공지 보강·선별

## 개요

`ai` 는 수집된 공지를 사용자에게 맞게 걸러내는 두 단계를 담당한다. **보강(enrich)** 은 공지당 1회, 사용자와 무관하게 LLM 을 호출해 3문장 요약·정리된 markdown·마감일을 채운다. **선별(classify)** 은 그 공지를 출처를 구독한 각 사용자의 관심 조건·프로필과 대조해 관련도(0~1)·매칭 키워드·선별 사유를 산출하고, 임계값 이상만 개인 피드(`InboxNotice`)로 편입한다. 선별은 단순 키워드 표면 일치가 아니라 LLM 이 문맥·의미로 판단한다.

LLM 클라이언트는 **제공자 비종속(OpenAI 호환)** 이다. 기본값은 가성비가 좋은 Google Gemini(`gemini-2.5-flash-lite`, 무료 티어 존재)이며 `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY` 세 값만 바꾸면 OpenAI·DeepSeek·Groq 등으로 교체된다. **키가 없거나 호출이 실패하면 예외를 던지지 않고 결정론적 키워드 매칭으로 폴백**하므로 오프라인/CI/데모에서도 파이프라인이 그대로 돈다. 이 앱은 HTTP 왕복 없이 Django ORM 을 직접 쓰며(관리 명령·서비스 함수), 유일한 HTTP 노출은 프론트 배너용 상태 조회다.

## 구성

| 파일 | 역할 |
| --- | --- |
| `llm.py` | `LLMClient`(OpenAI 호환 chat/completions, 429/503 재시도, 방어적 JSON 파싱, 키워드 폴백), `Verdict`·`Enrichment` 결과 타입, `first_sentences`(폴백 요약), `get_client` 팩토리 |
| `prompts.py` | 선별용 `SYSTEM_PROMPT`·`build_messages`, 보강용 `ENRICH_SYSTEM_PROMPT`·`build_enrichment_messages`(모두 한국어, 순수 JSON 출력 유도) |
| `enrich.py` | `enrich_notice`/`enrich_notices`(공지당 1회, 멱등), `parse_deadline`(LLM 마감일 문자열 → aware datetime) |
| `service.py` | `run_classification`(후보 공지 순회), `classify_notice`(공지 → 구독자 전체), `classify_notices_for_user`(공지들 → 한 사용자, 동기화용), `RunSummary` 집계 |
| `status.py` | `mark_degraded`/`mark_ok`/`get_status` — 429 폴백 전환/복구를 캐시 플래그로 남겨 배너에 반영 |
| `management/commands/classify_notices.py` | `manage.py classify_notices` — 선별 실행 진입점 |

## 흐름 · 사용법

파이프라인 위치: `crawl_notices` → **보강** → **선별(classify_notices)** → `dispatch_alerts`.

- **보강**은 크롤 직후 새 공지에 대해 `enrich_notices` 로 실행된다(스케줄러/`run_pipeline`/sync 가 호출). `notice.summary` 가 이미 있으면 건너뛴다(멱등).
- **선별**은 관리 명령으로 실행한다:

```bash
python manage.py classify_notices                 # 아직 AI 로 분류 안 된 신규 공지만
python manage.py classify_notices --since 24h      # 최근 24시간(30m/24h/7d/숫자=시간)
python manage.py classify_notices --source 3 --limit 50
python manage.py classify_notices --reclassify     # 이미 분류된 쌍도 재판정(LLM 재호출)
python manage.py classify_notices --dry-run        # 쓰지 않고 집계만
```

선별은 임계값(`LLM_RELEVANCE_THRESHOLD`, 기본 0.5) 이상이면 `InboxNotice` 를 upsert(멱등)하고, 미만이면 기존 행을 삭제(다운그레이드)해 오래된 높은 점수를 남기지 않는다. 사이트별 "동기화" 버튼은 이 명령 대신 `classify_notices_for_user` 를 직접 불러 요청 사용자·소수 공지만 처리한다(→ `sources` 앱).

이 앱은 관리 명령/서비스 함수로 동작하며, 외부에 노출하는 HTTP 엔드포인트는 `GET /api/ai/status/`(프론트 배너용, `notices` 앱이 라우팅) 하나뿐이다.

## 유의사항

- **비용 최소화(NFR-6)**: 보강은 공지당 1회, 선별은 `(공지,사용자)` 쌍당 1회만 LLM 을 부른다. 이미 AI 로 판정된 쌍은 `--reclassify` 없이는 재호출하지 않는다. 반면 크롤러의 순진한 매처가 남긴 `reason == "Keyword match"` 행은 아직 미판정으로 보고 AI 가 덮어쓴다.
- **`notified_at` 불가침**: 선별 upsert 는 `update_or_create` 의 defaults 에 `notified_at` 을 넣지 않아 알림 계층 소유 필드를 절대 건드리지 않는다.
- **폴백 안전**: `LLM_API_KEY` 가 비면 키워드 매칭으로, 429(사용량 소진)면 폴백 전환 + 배너 플래그(`status.py`)로 처리한다. 상태 캐시는 프로세스 지역(LocMemCache)이라 동기화 버튼을 누른 같은 웹 프로세스의 배너에 바로 반영된다.
- 관련도 임계값·모델·타임아웃·본문 상한은 모두 `settings`(→ `.env`)로 조정한다. 프론트는 별도로 관련도 0.8 이상을 "강한 AI 추천"으로 강조한다(`frontend/src/utils/relevance.js`).
