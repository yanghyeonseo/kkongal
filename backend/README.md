# backend — 꽁알꽁알 Django 서버

## 개요

꽁알꽁알 백엔드는 **Django 6 + Django REST Framework** 기반의 API 서버로, 공지 수집부터 AI 선별, 멀티채널 알림까지의 파이프라인을 오케스트레이션한다. 기능은 여섯 개의 앱으로 나뉜다 — 계정·관심사(`account`), 출처·구독(`sources`), 공지 원본·공지함(`notices`), 수집(`crawler`), LLM 보강·선별(`ai`), 알림 발송(`alert`). 인증은 SimpleJWT 를 쓰되 프론트의 쿠키 흐름에 맞춰 `access_token` 쿠키도 읽는다. 데이터베이스는 개발 편의를 위해 SQLite 이며, 비밀 값과 외부 연동(LLM·SMTP)은 모두 `.env` 로 관리한다.

## 구성

| 앱 | 책임 | 상세 |
| --- | --- | --- |
| `account` | 사용자·인증(쿠키 JWT)·관심 조건 | [account/README.md](account/README.md) |
| `sources` | 공지 출처(`NoticeSource`)·구독·카탈로그·온디맨드 동기화 | [sources/README.md](sources/README.md) |
| `notices` | 공지 원본(`Notice`)·사용자별 공지함(`InboxNotice`)·AI 상태 | [notices/README.md](notices/README.md) |
| `crawler` | 사이트별 스크래핑·저장·스케줄러 | [crawler/README.md](crawler/README.md) |
| `ai` | LLM 보강(요약·markdown·마감일)·의미 기반 선별 | [ai/README.md](ai/README.md) |
| `alert` | 이메일·슬랙 발송·비블로킹 연동 확인·중복 방지 | [alert/README.md](alert/README.md) |
| `kkongal/` | 프로젝트 설정(`settings.py`)·전체 라우팅(`urls.py`) | — |

데이터 모델의 상세 스키마와 ERD 는 [docs/data-model.md](../docs/data-model.md) 를 참고한다.

## 흐름 · 사용법

### 요청·인증 모델

프론트는 Vite dev 서버(3000)에서 `/api` 를 백엔드(8000)로 프록시하므로 브라우저 입장에서 same-origin 이고, 로그인 시 백엔드가 내려준 JWT 쿠키가 1st-party 로 오간다. 인증은 `account.authentication.CookieJWTAuthentication` 이 담당한다 — `Authorization: Bearer` 헤더 우선, 없으면 `access_token` 쿠키를 읽고, 만료/무효 토큰은 예외 대신 비인증으로 흘려 공개 엔드포인트를 막지 않는다. 보호 뷰는 `request.user.is_authenticated` 로 접근을 통제한다. API 명세는 실행 후 Swagger UI(`/api/schema/swagger-ui/`)에서 확인한다.

### 실행

```bash
cd backend
uv venv --python 3.12 .venv          # 또는: python3.12 -m venv .venv
uv pip install -r requirements.txt   # 또는: .venv/bin/pip install -r requirements.txt

cp .env.example .env                 # SECRET_KEY 등 값 채우기
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver # http://127.0.0.1:8000
```

`uv` 를 쓰면 `uv sync` → `uv run python manage.py ...` 로도 동일하게 실행된다.

### 파이프라인·명령

크롤 → 보강 → 선별 → 발송이 파이프라인의 4단계다.

```bash
python manage.py run_pipeline --crawl   # 크롤부터 끝까지 한 번에(스케줄러/cron 용)
python manage.py run_scheduler --once   # 크롤(due) → 보강 → 선별 → 발송 한 틱

# 단계별 개별 실행
python manage.py crawl_notices --source snu_cse_notice --no-match
python manage.py classify_notices
python manage.py dispatch_alerts
```

### 테스트

```bash
.venv/bin/python manage.py check                 # 설정/모델 무결성
.venv/bin/python manage.py test                  # 전체 스위트
.venv/bin/python manage.py test ai alert notices # 특정 앱만
```

테스트는 실제 LLM/이메일을 호출하지 않는다 — `LLM_API_KEY` 를 비우면 키워드 폴백으로, 이메일은 locmem/console 백엔드로 동작한다.

## 유의사항

- 공개 API 경로·응답 필드·모델은 프론트가 의존하는 계약이다. 내부 리팩터는 자유롭되 이 계약은 보존한다.
- `.env` 는 절대 커밋하지 않는다(`.env.example` 참고). 핵심 값: `SECRET_KEY`, `LLM_API_KEY`(선택), 이메일 `EMAIL_*`, `FRONTEND_URL`. 슬랙 Webhook 은 서버 설정이 아니라 사용자별로 웹 UI 에서 등록한다.
- **AI 선별은 관리 명령/서비스(ORM)로 동작**하며 별도 HTTP 계약을 두지 않는다. 외부에 노출되는 AI 엔드포인트는 프론트 배너용 `GET /api/ai/status/` 하나뿐이다.
- 별도의 데모 시드 명령은 없다. 테스트는 각 앱이 필요한 객체를 직접 만들어 검증한다.
- DB 는 SQLite(`db.sqlite3`)이고 스케줄러는 관리 명령 루프(`run_scheduler`)로 구현돼 있다 — 별도 브로커/워커가 필요 없다.
