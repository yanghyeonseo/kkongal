# 꽁알꽁알(Kkongal)

> 맞춤 공지 알리미 — 흩어진 공지를 한곳에서, AI가 필요한 것만 골라줍니다.

여러 사이트(채용 플랫폼, 학교·학부 공지, 관심 기업 채용 페이지 등)를 매일 따로 확인하는 **탐색 비용**을 줄여주는 웹 서비스입니다. 사용자가 관심 있는 사이트의 URL과 주제를 등록하면, 각 사이트의 공지 변화를 자동으로 감지·수집하고, LLM이 사용자의 관심사·조건에 맞는 공지만 선별해 하나의 대시보드로 모아 보여줍니다.

초기 구상과 세부 기획은 [IR Deck](docs/IR_Deck.pdf)에서, 서비스 소개는 [100초 피칭 영상](https://youtu.be/MK0nMy_avfU)에서 확인할 수 있습니다.

## 링크

- **배포 URL**: https://kkongal.cloud
- **프론트엔드 데모 (Figma)**: https://stung-arrow-75733307.figma.site
- **데이터 모델 ERD (FigJam)**: https://www.figma.com/board/JGuLClw7NbtdzpWPj89m27/Kkongal-ERD
- **팀 협업 문서 (Google Docs)**: https://docs.google.com/document/d/1npXftXwNEfNK-Dobz-ccwBmbsrjSprkRXEQQyNBNMSg/edit?usp=sharing

## 주요 기능

- **사이트 등록**: 관심 사이트의 URL·주제와 자신의 조건(직무·지역·고용 형태 등)을 입력하면 추적이 시작됩니다. 크롤링 기반이라 RSS를 제공하지 않는 사이트도 다룰 수 있습니다.
- **자동 감지·수집**: 등록된 사이트의 공지 영역을 주기적으로 확인해 변화를 감지하고, 제목·본문·게시일·변경 이력을 구조화해 저장합니다.
- **AI 기반 선별**: 단순 키워드 매칭이 아니라, LLM이 공지를 읽고 사용자의 관심사·조건에 부합하는지 의미 기준으로 판단해 필요한 것만 남깁니다.
- **통합 대시보드**: 선별된 공지를 출처·시간·관련도와 함께 한 화면에 모아 보여줍니다.
- **멀티채널 알림**: 새 공지가 올라오면 이메일, 카카오톡 알림톡, 슬랙 등 사용자가 선택한 채널로 전달합니다.

## 기술 스택

| 영역     | 사용 기술                                                    |
| -------- | ------------------------------------------------------------ |
| Frontend | React, TypeScript, Node.js                                   |
| Backend  | Python, Django, MySQL                                        |
| Crawler  | BeautifulSoup (정적 페이지), Playwright (동적·로그인 페이지) |
| AI       | LLM API                                                      |

## 디렉토리 구조

```
kkongal/
├── frontend/          # React + TypeScript 웹 클라이언트
├── backend/           # Django 서버 + MySQL
│   ├── crawler/       # 공지 수집 (BeautifulSoup / Playwright)
│   ├── ai/            # LLM 기반 공지 선별 로직
│   └── alert/         # 멀티채널 알림 발송 (메일 / 카카오 알림톡 / 슬랙)
└── docs/              # 문서
    └── kkongal.pdf    # IR Deck (발표 자료)
```

## 빠른 시작 (Quick Start)

### 1) 백엔드 (Django)

```bash
cd backend
uv venv --python 3.12 .venv          # 또는: python3.12 -m venv .venv
uv pip install -r requirements.txt   # 또는: .venv/bin/pip install -r requirements.txt

cp .env.example .env                 # 값 채우기 (아래 "환경 변수" 참고)
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo # (선택) 데모 데이터 시드
.venv/bin/python manage.py runserver # http://127.0.0.1:8000
```

### 2) 프론트엔드 (React + Vite)

```bash
cd frontend
npm install
npm run dev                          # http://localhost:3000 (→ /api 는 백엔드로 프록시)
```

> 개발 서버는 3000 포트에서 뜨고 `/api` 요청을 백엔드(127.0.0.1:8000)로 프록시하므로
> JWT 쿠키가 same-origin(first-party)으로 처리됩니다. CORS·SameSite 설정이 필요 없습니다.

### 3) AI 선별 → 알림 파이프라인 실행

```bash
# 개별 실행
.venv/bin/python manage.py crawl_notices --no-match   # 공지 수집(순진한 매칭 끔)
.venv/bin/python manage.py classify_notices           # AI 선별 → inbox_notice
.venv/bin/python manage.py dispatch_alerts            # 이메일/슬랙 발송

# 한 번에 (스케줄러/cron 용)
.venv/bin/python manage.py run_pipeline --crawl       # 크롤 → 선별 → 발송
```

## AI 선별 · 멀티채널 알림

이 저장소의 핵심 확장 기능입니다.

- **AI 선별 (`backend/ai/`)** — 크롤링된 공지를, 구독 사용자의 관심 조건(키워드 + 자연어 설명)과
  프로필을 근거로 **LLM이 의미 기준으로 판단**해 관련도(0~1)·매칭 키워드·선별 사유를 산출하고,
  임계값 이상만 개인 피드(`inbox_notice`)에 편입합니다.
  - **가성비 최상 기본값**: Google **Gemini 2.5 Flash‑Lite** (OpenAI 호환 엔드포인트, 무료 티어 존재).
  - **제공자 교체 자유**: `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY` 세 값만 바꾸면 OpenAI·DeepSeek·Groq 등으로 전환.
  - **키 없이도 동작**: `LLM_API_KEY`가 비면 결정적 키워드 매칭으로 폴백 → 데모/CI/오프라인 안전.
  - **비용 최소화(NFR‑6)**: 이미 분류된 공지는 재호출하지 않습니다.
- **멀티채널 알림 (`backend/alert/`)** — 선별된 미발송 공지를 사용자의 활성 채널로 발송합니다.
  - **이메일**: HTML+텍스트 본문. 기본 백엔드는 콘솔 출력이라 SMTP 없이도 데모됩니다.
  - **슬랙**: Incoming Webhook(Block Kit). 사용자는 웹 UI의 **알림 설정**에서 Webhook URL을 등록합니다
    (등록 방법은 입력란 옆 **? 도움말** 버튼 참고).
  - **중복 방지**: `inbox_notice.notified_at` 으로 재발송을 막고, 채널별 결과는 `alert_logs` 에 기록합니다.
  - **장애 격리(NFR‑3)**: 한 채널/사용자 실패가 전체 발송을 멈추지 않습니다.

### 환경 변수

모든 비밀 값은 `backend/.env` 로 관리하며 저장소에 커밋하지 않습니다(`.env.example` 참고).
핵심 항목: `SECRET_KEY`, `LLM_API_KEY`(선택), `LLM_MODEL`, 이메일 SMTP(`EMAIL_*`), `FRONTEND_URL`.
슬랙 Webhook은 서버 설정이 아니라 **사용자별로 웹 UI에서** 등록합니다.

## 팀

| 이름   | GitHub                                           | 역할                                       |
| ------ | ------------------------------------------------ | ------------------------------------------ |
| 양현서 | [@yanghyeonseo](https://github.com/yanghyeonseo) | AI 선별·알림 기능 / 프론트·백엔드 지원     |
| 서지안 | [@Seo-Jian](https://github.com/Seo-Jian)         | 프론트엔드 (대시보드·사이트 등록 UI)       |
| 윤지후 | [@jeehooy2](https://github.com/jeehooy2)         | 백엔드 (크롤링·수집 파이프라인, 서버 로직) |
| 배진규 | [@r2rboss1](https://github.com/r2rboss1)         | 백엔드 (크롤링·수집 파이프라인, 서버 로직) |
