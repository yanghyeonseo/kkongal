# kkongal — 요구사항 및 명세 (Requirements & Specifications)

> 맞춤 공지 알리미. 여러 사이트의 공지를 자동 수집하고, LLM 으로 사용자에게 필요한 것만 선별해 통합 대시보드와 멀티채널 알림(이메일·슬랙)으로 제공한다.

본 문서는 SNU Likelion 해커톤(2026.07.03~07.04) 구현의 요구사항과 명세다. 초기 스펙을 기준으로 하되, **실제 구현(as-built)과 달라진 부분은 각 절에 `[as-built]` 로 표시**한다. 상세 스키마는 [data-model.md](data-model.md) 를 참고한다.

---

## 1. 개요

### 1.1 문제 정의

관심 있는 공지(채용, 학교·학부, 장학금·공모전 등)가 여러 사이트에 흩어져 있어, 사용자는 매일 여러 사이트를 직접 돌며 확인해야 한다. 이 **탐색 비용**이 크고, 놓치는 공지가 생긴다.

### 1.2 솔루션 요약

1. 사용자가 관심 사이트(URL·주제)와 본인의 관심 조건을 등록한다.
2. 시스템이 각 사이트를 주기적으로 크롤링해 새 공지를 수집한다.
3. 공지를 공지당 1회 보강(요약·마감일)하고, LLM 이 사용자 조건에 맞는지 의미 기준으로 선별한다.
4. 선별된 공지를 통합 대시보드에 모아 보여주고, 선택한 채널로 알림을 보낸다.

### 1.3 용어 정의

| 용어         | 의미                                        |
| ------------ | ------------------------------------------- |
| Source(소스) | 등록한 공지 출처 사이트                     |
| Notice(공지) | 소스에서 수집한 개별 게시물                 |
| Alert(알림)  | 선별된 공지를 사용자에게 내보내는 발송 행위 |
| Filter(조건) | 공지 선별에 쓰이는 사용자의 관심 기준(`interests`) |

---

## 2. 시스템 아키텍처

### 2.1 구성 요소 `[as-built]`

- **Frontend** (React 19 + Vite, JavaScript): 랜딩, 온보딩, 대시보드, 사이트/관심사/알림 채널 설정 UI
- **Backend / API** (Django 6 + DRF, SQLite): 인증(쿠키 JWT), 소스·공지·채널 관리, 보강·선별·발송 오케스트레이션
- **Crawler** (httpx + BeautifulSoup/lxml): 정적 HTML 페이지에서 공지 수집. *(초기 스펙의 Playwright 동적/로그인 수집은 현재 범위에서 미구현)*
- **AI** (OpenAI 호환 LLM, 기본 Google Gemini): 공지 보강 + 관련도 판단·선별. 키 없음/실패 시 키워드 폴백
- **Alert** (이메일 SMTP · 슬랙 Incoming Webhook): 선별 결과 발송. *(카카오 알림톡은 승인 리드타임으로 후순위)*

### 2.2 데이터 흐름 `[as-built]`

```
[사용자] → 소스/조건 등록 → [Backend/SQLite]
                                  │
            (스케줄러 주기 실행)    ▼
                              [Crawler] → 새 공지 수집·정규화 → [Notice]
                                  │
                                  ▼
                              [AI 보강] → 공지당 1회 요약·markdown·마감일
                                  │
                                  ▼
                              [AI 선별] → 사용자 조건과 매칭, 관련도 산정 → [InboxNotice]
                                  │
                          ┌───────┴───────┐
                          ▼               ▼
                   [대시보드 표시]      [Alert 발송: 이메일/슬랙]
```

파이프라인 4단계: **crawl → enrich → classify → dispatch**.

---

## 3. 기능 요구사항 (Functional Requirements)

### 3.1 계정 / 인증

- **FR-1** 사용자는 가입하고 로그인할 수 있다. `[as-built]` 자체 회원가입(**username + 비밀번호**), 쿠키 기반 JWT.
- **FR-2** 사용자는 알림 수신에 필요한 이메일 등 본인 정보를 등록·수정할 수 있다. `[as-built]` 가입 시 이메일 필수(유니크). 가입 후 온보딩(관심사·채널·사이트).

### 3.2 소스(공지 출처) 등록·관리

- **FR-3** 사용자는 추적할 사이트의 URL 을 등록할 수 있다. `[as-built]` 카탈로그 선택 또는 임의 URL 등록.
- **FR-4** 사용자는 등록한 소스 목록을 조회·수정(표시명)·삭제할 수 있다.
- **FR-5** 시스템은 사이트별 스크래퍼로 수집 방식을 적용한다. `[as-built]` 카탈로그(`sites.json`)의 `scraper` 로 결정.
- **FR-6** _(미구현)_ 로그인이 필요한 사이트 등록은 현재 범위에서 제외.

### 3.3 크롤링 / 수집

- **FR-7** 시스템은 등록된 각 소스를 주기적으로 확인해 새 공지를 감지한다. `[as-built]` `run_scheduler` 가 due 사이트를 크롤.
- **FR-8** 시스템은 공지의 제목·본문·원문 링크·게시일을 구조화해 저장한다. `[as-built]` 추가로 요약·markdown·마감일을 AI 보강.
- **FR-9** 시스템은 이미 수집한 공지와 신규 공지를 구분해 중복을 막는다. `[as-built]` 동일성 `(source_id, url)`, 알림 중복은 `notified_at`.
- **FR-10** 정적 페이지를 BeautifulSoup 으로 수집한다. `[as-built]` 정적 HTML 만 지원(Playwright 동적 수집은 미구현).

### 3.4 AI 선별

- **FR-11** 사용자는 관심 조건을 입력할 수 있다. `[as-built]` 키워드 + 자연어 설명 + 우선순위(`interests`).
- **FR-12** 시스템은 수집 공지가 사용자 조건에 부합하는지 LLM 으로 판단한다. `[as-built]` 키 없음/실패 시 키워드 폴백.
- **FR-13** 선별 결과에 관련도와 선별 사유를 함께 저장한다. `[as-built]` `relevance_score`·`reason`·`matched_keywords`.
- **FR-14** 조건에 부합하지 않는(임계값 미만) 공지는 피드/알림 대상에서 제외한다.

### 3.5 대시보드

- **FR-15** 사용자는 선별 공지를 출처·게시일·관련도와 함께 한 화면에서 본다.
- **FR-16** 사용자는 공지를 출처·관심사·기간(마감임박/마감)·검색으로 필터링/정렬한다.
- **FR-17** 사용자는 공지 원문 링크로 이동한다.
- **FR-18** 사용자는 공지를 읽음/저장 처리할 수 있다. `[as-built]` 구현됨(`is_read`·`is_saved`).

### 3.6 멀티채널 알림 (Alert)

- **FR-19** 사용자는 알림 채널을 선택·연동할 수 있다. `[as-built]` 이메일·슬랙(카카오는 예약값, 발송기 없음).
- **FR-20** 새로 선별된 공지가 있으면 선택한 채널로 발송한다.
- **FR-21** 발송 결과(성공/실패)를 이력(`alert_logs`)으로 기록한다.
- **FR-22** _(부분)_ 채널 생성 직후 연동 확인 메시지를 비블로킹으로 발송. 알림 빈도 설정은 미구현.

---

## 4. 비기능 요구사항 (Non-functional Requirements)

- **NFR-1 (보안)** 인증 정보·외부 연동 토큰·API 키는 평문 노출 없이 보관한다. 비밀 값은 환경 변수(`.env`)로 관리하며 커밋하지 않는다.
- **NFR-2 (개인정보)** 알림 채널 연동 정보(슬랙 webhook 등)는 최소 범위로 수집·저장한다. 슬랙 webhook 은 `hooks.slack.com` 으로만 제한(SSRF 방어).
- **NFR-3 (안정성)** 한 소스의 크롤링 실패, 한 채널/사용자의 발송 실패가 다른 소스 수집·발송이나 전체 파이프라인을 중단시키지 않는다.
- **NFR-4 (확장성)** 새로운 알림 채널을 발송기 인터페이스 추가만으로 확장할 수 있다(`BaseSender` + `SENDER_REGISTRY`).
- **NFR-5 (예의 바른 크롤링)** 합리적 요청 간격(`request_delay_seconds`)을 준수한다.
- **NFR-6 (비용)** LLM 호출은 신규/미분류 공지에만 적용한다. 보강은 공지당 1회, 선별은 `(공지,사용자)` 쌍당 1회로 재호출을 억제한다.

---

## 5. 데이터 모델 (개략)

> 확정·상세 스키마(as-built)는 [데이터 모델 문서](data-model.md)를 참고. 핵심 엔티티: `User`·`Interest`·`NoticeSource`·`SourceSubscription`·`Notice`·`InboxNotice`·`AlertChannel`·`AlertLog`.

---

## 6. 외부 연동

| 연동            | 용도      | 상태 |
| --------------- | --------- | --- |
| LLM API (OpenAI 호환) | 공지 보강·선별 | `[as-built]` 기본 Google Gemini, 키 없으면 키워드 폴백 |
| 이메일(SMTP)    | 알림 발송 | `[as-built]` 기본 콘솔 백엔드, SMTP 전환 시 587/465 지원 |
| 슬랙            | 알림 발송 | `[as-built]` Incoming Webhook, 사용자별 등록 |
| 카카오 알림톡   | 알림 발송 | _(후순위)_ 템플릿 사전 승인 리드타임으로 현재 범위 제외 |

---

## 7. API 명세 (개요) `[as-built]`

> 상세는 Swagger UI(`/api/schema/swagger-ui/`)에서 확인. 인증은 쿠키의 `access_token`(또는 Bearer 헤더).

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| POST | `/api/account/signup/` · `/api/account/signin/` | 가입 · 로그인 |
| POST | `/api/account/refresh/` · `/api/account/logout/` | 토큰 재발급 · 로그아웃 |
| GET | `/api/account/me/` | 현재 사용자 |
| POST | `/api/account/onboarding/complete/` | 온보딩 완료 |
| GET/POST | `/api/interests/` | 관심 조건 조회 / 생성 |
| PUT/DELETE | `/api/interests/{id}/` | 관심 조건 수정 / 삭제 |
| GET/POST | `/api/subscriptions/` | 구독 목록 / 등록 |
| DELETE | `/api/subscriptions/{id}/` | 구독 해제 |
| GET | `/api/sources/catalog/` | 지원 사이트 카탈로그 |
| PATCH | `/api/sources/{id}/` | 사이트 표시명 편집 |
| POST | `/api/sources/{id}/sync/` | 온디맨드 동기화 |
| GET | `/api/notices/inbox/` | 선별 공지 목록(필터 지원) |
| GET | `/api/notices/inbox/{id}/` | 공지 상세 |
| PATCH | `/api/notices/inbox/{id}/save/` · `/read/` | 저장 · 읽음 상태 변경 |
| GET | `/api/ai/status/` | AI 가용 상태(배너용) |
| GET/POST | `/api/alert-channels/` | 채널 조회 / 생성 |
| PATCH/DELETE | `/api/alert-channels/{id}/` | 채널 수정 / 삭제 |
| POST | `/api/alert-channels/{id}/test/` | 테스트 발송 |
| GET | `/api/alert-logs/` | 발송 로그 |
| (internal) | `run_pipeline` · `run_scheduler` · `crawl_notices` · `classify_notices` · `dispatch_alerts` | 관리 명령(스케줄러가 트리거) |

---

## 8. 구현 스택 (확정) `[as-built]`

- Frontend: React 19, Vite, JavaScript(JSX), lucide-react
- Backend: Python 3.12, Django 6, Django REST Framework, SQLite
- Crawler: httpx, BeautifulSoup(lxml), pydantic — 정적 HTML
- AI: OpenAI 호환 LLM(기본 Google Gemini 2.5 Flash‑Lite)
- Alert: 이메일(SMTP), 슬랙(Incoming Webhook)
- 배포: kkongal.cloud

---

## 9. 구현 범위 (해커톤 결과)

**구현됨 (Must + Should)**

- 소스 등록(정적 페이지) → 주기 크롤링 → 공지 저장
- 공지 AI 보강(요약·markdown·마감일)
- 사용자 조건 입력 → LLM 선별(키워드 폴백 포함)
- 대시보드에서 선별 공지 확인(필터·검색·읽음·저장)
- 온디맨드 사이트 동기화
- 알림 채널 2종(이메일·슬랙) 발송 + 발송 로그

**미구현 / 후순위 (Could / Post-hackathon)**

- 동적·로그인 사이트(Playwright) 수집
- 카카오 알림톡(승인 리드타임)
- 정교한 변경 감지, 알림 빈도(즉시/요약) 설정

---

## 10. 성공 기준 (Acceptance)

- 사용자가 소스와 조건을 등록하면, 신규 공지 중 조건에 맞는 항목만 대시보드에 나타난다.
- 조건에 맞는 신규 공지 발생 시 최소 1개 채널로 알림이 도달한다.
- 동일 공지가 중복으로 알림되지 않는다(`notified_at`).

---

## 11. 결정 사항 (Decisions) — 확정·구현 완료

- **Q1. 인증 방식** → 자체 회원가입(**username + 비밀번호**), 쿠키 기반 JWT. (초기 스펙의 이메일 로그인 대신 username 인증, 이메일은 알림용 필수 필드.)
- **Q2. 공지 영역 추출** → 카탈로그(`sites.json`)의 사이트별 스크래퍼로 안정 추출. 사용자 임의 URL 등록도 지원하되 자동 수집은 카탈로그 사이트만.
- **Q3. 로그인 필요 사이트** → 현재 범위 제외(미구현).
- **Q4. 조건 입력 형태** → 키워드 + 자연어 설명 + 우선순위(`interests`).
- **Q5. 중복/변경 판정** → 동일성 `(source_id, url)`. 알림 중복은 `notified_at`.
- **Q6. 알림 채널** → 이메일 + 슬랙 구현. 카카오는 후순위(예약값만 존재).
- **Q7. 크롤링 주기** → `crawl_interval_minutes` 소스별 설정(**기본 60분**), `run_scheduler` 루프.
