# 계획: 임의 사이트 추가 + 로그인 사이트 공지 트래킹

> 상태: **계획(Planning)** — 구현 전. 데모 전제, 중앙 클라우드 배포.

## 1. 목표

1. **기능 1 — 어떤 사이트든 링크로 추가**: `sites.json`의 손파서가 없는 임의 URL도 공지 목록을 자동 추출·트래킹.
2. **기능 2 — 로그인 사이트 트래킹**: 사용자가 아이디/비밀번호를 등록하면, 서버가 대신 로그인해 인증이 필요한 페이지의 공지를 트래킹.

## 2. 확정된 결정(이전 논의 요약)

- **배포**: 중앙 클라우드. → 공개 사이트(기능 1)는 완전 유효. 인증 세션 재생은 IP바인딩/WAF 사이트에서 제한적임을 인지.
- **인증 방식**: **아이디/비밀번호를 암호화해 DB 저장**, 서버가 Playwright로 자동 로그인. (데모라 이 방식 채택 — 보안 트레이드오프는 아래 §9에 명시.)
- **제외**: 브라우저 확장(비용), 세션 paste/헬퍼 CLI(UX), 평문 저장.

## 3. 현재 구조와 격차

- **등록**: `SourceSubscriptionCreateSerializer`가 이미 임의 URL 허용 → `NoticeSource` 생성됨. **등록 자체는 이미 동작.**
- **크롤**: `SourceSyncView`가 `source.url`을 `sites.json`과 매칭, 없으면 `400 "자동 수집 미지원"`. 스크래퍼는 `crawler/scrapers/REGISTRY`에 사이트별 하드코딩. `fetcher.py`는 순수 `httpx.GET`(JS·쿠키 없음).
- **결론**: 만들 것 = (a) 임의 사이트용 **generic 추출 파이프라인**, (b) 스크래퍼 해석을 `sites.json` → `NoticeSource` 기준으로 분리, (c) **로그인/렌더용 Playwright 백엔드 + 자격증명 저장**.

## 4. 아키텍처 개요

```
등록(URL[, 로그인정보]) → NoticeSource(+SourceCredential)
        │
   스크래퍼 해석 (NoticeSource.scraper_kind 기준)
        │
   ┌────┴─────────────────────────────┐
   │ builtin   → 기존 REGISTRY 파서     │
   │ generic   → RSS→휴리스틱→LLM 학습  │  ← 기능 1
   └──────────────────────────────────┘
        │  fetch (render 백엔드)
   ┌────┴──────────────────────────┐
   │ http    → httpx (+세션 쿠키)    │
   │ browser → Playwright(+로그인)   │  ← 기능 2
   └───────────────────────────────┘
        │
   기존 파이프라인: 저장 → 보강 → AI선별 → 알림
```

## 5. 데이터 모델 변경

### 5.1 `NoticeSource` 필드 추가 (`sources/models.py`)
- `scraper_kind`: `CharField` — `builtin | rss | heuristic | llm_profile` (기본 추론값). 크롤 성공 시 확정·저장.
- `extraction_profile`: `JSONField(null=True)` — 학습된 셀렉터 레시피(`list_selector`, `title`, `link`, `date`) 또는 RSS 피드 URL.
- `render`: `CharField` — `http | browser` (기본 `http`, JS 필요 시 `browser`로 승격).
- `requires_auth`: `BooleanField(default=False)`.
- `last_extract_ok_at`: `DateTimeField(null=True)` — 마지막으로 1건 이상 추출 성공한 시각(프로파일 stale 판정용).

### 5.2 신규 모델 `SourceCredential` (`sources/models.py`)
사용자·소스별 로그인 정보. **user+source 유니크.**
- `user_id` FK, `source_id` FK
- `login_url`: 로그인 폼 페이지 URL(비면 소스 URL에서 탐지 시도)
- `username`: 평문(식별자, 민감도 낮음) 또는 암호화 — §9 참고
- `password_encrypted`: `BinaryField` — Fernet 암호문
- `storage_state_encrypted`: `BinaryField(null=True)` — 로그인 후 캡처한 Playwright storageState(재로그인 최소화)
- `field_hints`: `JSONField(null=True)` — 폼 셀렉터 수동 지정(자동탐지 실패 대비)
- `status`: `CharField` — `active | needs_reauth | unsupported | error`
- `last_login_at`, `last_error`: 진단용

### 5.3 마이그레이션
- `sources` 앱에 마이그레이션 2개(필드 추가 / 신규 모델). 기존 데이터는 `scraper_kind=builtin`(카탈로그 URL) 또는 `generic`으로 backfill.

## 6. 기능 1 — Generic 추출 파이프라인

**신규 `crawler/scrapers/generic.py`** — 비용 싼 순서로 계단식. 결과를 `NoticeSource`에 학습·캐시.

1. **RSS/Atom 자동탐지**
   - `<link rel="alternate" type="application/rss+xml|atom+xml">`, 관용 경로(`/rss`, `/feed`, `/atom.xml`, `/rss.xml`) 시도.
   - 발견 시 피드 파싱(`feedparser`) → 제목/URL/게시일. `extraction_profile={"feed": url}`, `scraper_kind=rss` 저장.
2. **휴리스틱 반복블록 추출**
   - 페이지에서 "날짜를 가진 링크가 반복되는 지배적 블록" 탐지.
   - 기존 `base.py`의 `find_row_date`, `safe_href`, `_PURE_DATE_RE`, `first_text` 재사용.
   - 성공 시 `scraper_kind=heuristic`, 안정 셀렉터를 `extraction_profile`에 저장.
3. **LLM 셀렉터 학습(1회성)**
   - 앞 둘 실패 시 `ai/llm.py`로 정리된 HTML을 주고 셀렉터 레시피 도출.
   - `extraction_profile={list, title, link, date}`, `scraper_kind=llm_profile` 저장 → **이후 크롤은 LLM 없이 재사용**.
   - `last_extract_ok_at` 대비 크롤이 0건이면 프로파일 stale → 다음 크롤에서 재학습.

**해석 분리** (`crawler/scrapers/__init__.py` / `service.py`)
- 스크래퍼 선택을 `NoticeSource.scraper_kind`로 결정. builtin URL이면 기존 REGISTRY, 아니면 generic.
- `NoticeCrawlService`/`repository`가 config `SiteConfig`뿐 아니라 `NoticeSource`도 받도록 확장(현재 `config.site(source_id)` 강결합 완화).

**게이트 제거** (`sources/views.py` `SourceSyncView`)
- `sites.json` 매칭 없으면 `400` 내던 로직 제거 → generic 경로로 흘려보냄. `sync_jobs.run_sync_for_source`도 동일하게 config-site 강제 해제.

**안전장치**: robots.txt 존중, 도메인당 요청 딜레이(기존 `request_delay_seconds`), 실패는 기존처럼 `report.errors`로 흡수.

## 7. 기능 2 — 로그인 사이트 (Playwright + 자격증명)

### 7.1 렌더 백엔드 추가 (`crawler/fetcher.py`)
- `render:"http"` → 기존 httpx.
- `render:"browser"` → Playwright(chromium headless). 컨텍스트에 storageState 주입해 인증 상태로 페이지 로드.
- 세션만 있으면 정적 사이트는 httpx에 `Cookie` 헤더 실어 재생(브라우저는 JS 필요 시에만) — 비용 절감.

### 7.2 로그인 자동화 (`crawler/auth.py` 신규)
데모용 **generic 폼 필러**(사이트별 레시피 없이 최대한 커버):
1. `login_url`(없으면 소스 URL) 로드.
2. 사용자명 필드 = `input[type=email]` / `input[name*=user|id|login]` / password 앞의 text 입력, 비번 = `input[type=password]`. (`field_hints`로 수동 오버라이드 가능.)
3. 값 채우고 submit(폼 submit 또는 `button[type=submit]`).
4. 네비게이션 대기 후 로그인 성공 판정(로그인 폼 사라짐 / URL 변화).
5. 성공 시 `storageState` 캡처 → `storage_state_encrypted`에 저장, `status=active`, `last_login_at` 갱신.
6. 실패/2FA·CAPTCHA 감지 시 `status=unsupported|needs_reauth`, `last_error` 기록.

### 7.3 세션 재사용 & 만료 처리
- 크롤 시 저장된 storageState 우선 사용. 로그인 페이지로 리다이렉트/셀렉터 0건이면 → 저장된 자격증명으로 **자동 재로그인** 1회 시도 → 갱신 storageState 저장(self-healing).
- 재로그인도 실패하면 `status=needs_reauth` → 프런트에 노출.

### 7.4 데이터 격리 (중요)
- 인증 소스로 가져온 공지는 **해당 사용자에게만** 노출해야 함(현재 `Notice`는 소스 공용 → 유출 위험).
- 방안: `Notice`에 `private_to_user`(nullable FK) 또는 인증 소스 전용 저장 경로. `SourceSubscription` 단위로 가시성 제한. → §11 열린 질문.

## 8. 프런트엔드 변경 (`frontend/src`)

- **사이트 추가 UI**: 이미 임의 URL 입력 가능. "이 사이트는 로그인이 필요해요" 토글 추가 → 로그인 URL / 아이디 / 비번 입력(선택).
- **소스 상태 표시**: `scraper_kind`(자동수집 방식)·인증 `status`(연결됨 / 재인증 필요 / 지원 안 됨) 뱃지.
- **재인증 플로우**: `needs_reauth` 소스에 "비밀번호 다시 입력" 액션.
- API: `POST /api/subscriptions/`에 선택적 자격증명 필드 확장 또는 별도 `POST /api/sources/<id>/credential/`.

## 9. 보안 (데모 전제 — 리스크 명시)

> 데모라 아이디/비번 저장을 채택하지만, **실서비스로 갈 경우 재검토 필수.**

- **암호화**: `cryptography` Fernet. 키는 `settings.CREDENTIAL_ENC_KEY`(환경변수), `SECRET_KEY`와 **분리**. 절대 리포지토리/로그에 커밋 금지.
- **복호화 노출 금지**: 비번을 API 응답·직렬화·로그·LLM 프롬프트에 절대 포함하지 않음(쓰기 전용 필드). `Notice` 저장/알림 경로로 자격증명이 새지 않게.
- **한계(문서화)**: 백그라운드 크롤은 사용자 없이 복호화 → 키가 서버 상주 → 서버/DB/키 동시 유출 시 실제 비번 유출. 제로지식 불가. 사용자에게 "전용 비번 사용 권장" 안내.
- **전송**: HTTPS 필수(기존 TLS 하드닝 방침과 일치).

## 10. 의존성 / 운영

- 신규: `playwright`(+ `playwright install chromium`), `feedparser`, `cryptography`.
- 배포 이미지에 Chromium/시스템 라이브러리 포함(Dockerfile/빌드 갱신).
- Playwright는 무거움 → `sync_jobs` 순차 워커에서 **브라우저 컨텍스트 재사용**, 동시성 제한. LLM 스로틀과 유사하게 관리.
- 크롤러 큐가 인메모리(LocMemCache)라 다중 프로세스 배포 시 상태 공유 필요 — 기존 `sync_jobs` 주석의 Redis/DB 권고와 연동해 검토.

## 11. 열린 질문 / 리스크

1. **데이터 격리 방식**: `Notice`에 소유자 필드 추가 vs 인증 소스 전용 저장. 스키마 영향 큼 → 결정 필요.
2. **generic 추출 품질**: 사이트 다양성상 휴리스틱 실패율 존재. LLM 폴백 비용/정확도 트레이드오프 튜닝 필요.
3. **로그인 폼 다양성**: generic 폼 필러가 SSO·다단계·JS 로그인에서 실패 가능 → `field_hints` 수동 지정으로 보완, 그래도 안 되면 `unsupported`.
4. **클라우드 IP 재생 제약**: IP바인딩/WAF 사이트는 로그인 성공해도 크롤 실패 가능 → probe로 조기 감지·통보.
5. **법적/ToS**: 로그인 사이트 스크래핑은 약관 위반 소지. 데모 범위에 한정.

## 12. 단계별 로드맵 (구현 순서)

1. **모델·해석 분리**: `NoticeSource` 필드 + `SourceCredential` 모델 + 마이그레이션. 스크래퍼 해석을 소스 기준으로, `SourceSyncView` 400 게이트 제거. *(기능 1·2 공통 뼈대)*
2. **RSS + 휴리스틱 generic 스크래퍼**: LLM 없이 다수 커버. *(기능 1 대부분)*
3. **LLM 셀렉터 학습·캐시**. *(기능 1 완성)*
4. **Playwright 렌더 백엔드** + httpx 쿠키 재생. *(JS·인증 기반)*
5. **자격증명 암호화 저장 + 자동 로그인 + 세션 self-healing + 데이터 격리**. *(기능 2 완성)*
6. **프런트엔드**: 로그인 정보 입력 UI + 상태 뱃지 + 재인증.
7. **테스트**: generic 추출 단위 테스트(픽스처 HTML), 암호화 왕복, 로그인 자동화 모킹, 격리 접근제어.

## 13. 테스트 전략

- **generic 추출**: 대표 레이아웃(테이블 게시판, 카드 리스트, RSS) 픽스처로 파서 단위 테스트.
- **암호화**: Fernet 암·복호 왕복 + 응답 직렬화에 비번 미노출 검증.
- **로그인 자동화**: Playwright 모킹/로컬 픽스처 로그인 폼으로 성공·실패·2FA 감지 경로.
- **격리**: 타 사용자가 인증 소스 공지에 접근 불가함을 접근제어 테스트로 보장.
- 기존 `crawler/tests.py`, `sources` 테스트 패턴 준수.
