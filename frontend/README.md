# frontend — 꽁알꽁알 웹 클라이언트

## 개요

프론트엔드는 **React 19 + Vite** 단일 페이지 앱(JavaScript/JSX)이다. 로그인 상태와 온보딩 완료 여부에 따라 랜딩 → 온보딩 위저드 → 대시보드로 화면이 전환되는 상태 머신을 `App.jsx` 가 관리한다. 대시보드는 AI 가 선별한 개인 공지함을 카드로 보여주고, 사이트별/전체 온디맨드 동기화, 관심사·알림 채널 설정, AI 저하 배너를 제공한다. 아이콘은 `lucide-react`, 알림 UX 는 자체 토스트를 쓰며, 별도 라우터·상태관리 라이브러리 없이 React 상태와 얇은 API 계층으로 구성된다. 인증은 백엔드가 내려준 JWT 쿠키(same-origin 프록시)로 처리한다.

## 구성

```
frontend/
├─ index.html               # 진입 HTML(제목·favicon)
├─ vite.config.js           # dev 서버(3000) + /api → 127.0.0.1:8000 프록시
├─ public/                  # favicon 등 정적 자산
└─ src/
   ├─ main.jsx              # createRoot + ToastProvider
   ├─ App.jsx               # 최상위 뷰 라우팅·대시보드 상태·필터
   ├─ App.css / index.css   # 디자인 토큰·전역 스타일
   ├─ assets/               # logo.png(브랜드 로고), hero 이미지 등
   ├─ api/                  # 백엔드 호출 계층(엔드포인트별 모듈)
   ├─ components/           # 화면·모달·조각 컴포넌트
   ├─ context/toast.js      # 토스트 컨텍스트/훅
   └─ utils/                # relevance.js(AI 강조 기준), date.js(상대시간·D-day)
```

| 영역 | 파일 | 역할 |
| --- | --- | --- |
| API | `client.js` | 공통 `apiRequest` — same-origin + `credentials:"include"`(HttpOnly 인증 쿠키 자동 전송, JS 토큰 취급 없음), 401 시 refresh 후 1회 재시도(dedupe), refresh 마저 실패하면 세션 만료 핸들러(`setUnauthorizedHandler`) 호출, `ApiError` |
| API | `authApi.js` | me/signup/signin/logout/onboarding, user 정규화, localStorage 캐시 |
| API | `inboxApi.js` | 공지함 조회·저장·읽음(응답을 카드용 형태로 정규화, 마감 D-day 계산) |
| API | `sourceApi.js` | 구독 목록/등록/삭제, 카탈로그, 표시명 편집, 동기화 |
| API | `interestApi.js` | 관심사 항목 CRUD |
| API | `alertApi.js` | 알림 채널 CRUD·테스트 발송(429/404 친절 처리) |
| API | `aiApi.js` | `GET /api/ai/status/` 조회(실패 시 정상으로 간주) |
| 화면 | `Landing.jsx` | 비로그인 마케팅 랜딩(히어로·CTA) |
| 화면 | `OnboardingWizard.jsx` | 3단계 온보딩(관심사·알림 채널·사이트) |
| 화면 | `Header.jsx` / `Sidebar.jsx` | 상단바(로고·검색·메뉴) / 좌측 뷰·소스 목록·동기화 |
| 조각 | `NoticeCard.jsx`·`NoticeDetailModal.jsx`·`Markdown.jsx` | 공지 카드·상세 모달·markdown 렌더 |
| 모달 | `AuthModal`·`SiteRegisterModal`·`SiteCatalog`·`InterestSettingModal`·`AlertSettingsModal`·`SlackWebhookHelp` | 로그인/가입·사이트 등록·카탈로그·관심사·알림 설정·슬랙 도움말 |
| 공통 | `ModalShell.jsx`·`ToastProvider.jsx`·`SourceFavicon.jsx` | 접근성 모달 셸(포커스 트랩·Esc)·토스트·파비콘(폴백) |

## 흐름 · 사용법

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000 (/api 는 백엔드로 프록시)
npm run build      # 프로덕션 번들
npm run lint       # oxlint
```

dev 서버는 3000 포트에서 뜨고 `/api` 요청을 백엔드(127.0.0.1:8000)로 프록시하므로, 브라우저 입장에서 프론트와 API 가 same-origin 이 되어 JWT 쿠키가 1st-party 로 저장되고 CORS·SameSite 설정이 필요 없다.

**핵심 흐름**

- **랜딩 → 인증**: 최초 진입 시 `getCurrentUser`(`/api/account/me/`)로 쿠키 세션을 복원한다. 로그인 사용자가 없으면 `Landing` 을 보여주고, `AuthModal` 에서 로그인/가입한다.
- **온보딩**: 로그인했지만 `onboarded === false` 면 `OnboardingWizard` 로 진입한다. ①관심 키워드 등록(진행하며 즉시 저장) ②알림 채널(이메일 기본 + 슬랙 선택, `?` 도움말) ③사이트 카탈로그 선택 → "시작하기" 시 `completeOnboarding`(`/api/account/onboarding/complete/`) 후 대시보드로 전환한다.
- **대시보드**: `getMyInboxNotices`·`getNoticeSources`·`getMyInterests` 를 병렬로 불러 공지 카드·사이드바·관심사 필터를 그린다. 뷰(전체/AI 추천/저장), 카테고리(마감임박/마감), 관심사 칩, 검색으로 필터링하고 페이지네이션한다. 카드를 열면 상세 모달이 열리며 즉시 읽음 처리된다(`markInboxNoticeRead` 로 서버에도 저장).
- **동기화**: 사이드바의 사이트별/전체 동기화 버튼이 `syncSource`(`POST /api/sources/<id>/sync/`)를 호출해 즉시 크롤·선별하고 공지함을 새로고침한다. 결과 건수를 토스트로 알린다.
- **알림 설정**: `AlertSettingsModal` 에서 이메일·슬랙 채널을 추가/삭제하고 테스트 발송한다. 채널 생성 응답의 `confirmation` 은 연동 확인 발송의 best-effort 상태다.
- **AI 상태 배너**: 대시보드 로드·동기화 후 `getAiStatus`(`/api/ai/status/`)를 조회해, 저하 상태(`quota`/`disabled`)면 상단 배너로 "키워드 기반 임시 동작 중"을 안내한다(세션 내 닫기 기억, 정상 복귀 시 초기화).

## 유의사항

- **TypeScript 가 아니라 JavaScript/JSX** 다(`@types/*` 는 에디터 힌트용 devDependency). 라우터·전역 상태 라이브러리는 쓰지 않는다.
- API 계층은 백엔드 스네이크케이스 응답을 카멜케이스 뷰 모델로 **정규화**한다. 백엔드 계약(`snake_case`)이 바뀌면 해당 `api/*.js` 의 정규화 함수를 함께 고쳐야 한다.
- 인증 흐름(`credentials:"include"` 로 HttpOnly 쿠키 자동 전송, 401 refresh 재시도, 재발급 실패 시 세션 만료 처리)은 `client.js` 에 집약돼 있으니 개별 호출에서 토큰을 다루지 않는다.
- 마감 상태(임박 0~7일 / 지남)와 "강한 AI 추천"(관련도 0.8 이상 또는 매칭 태그 존재)은 프론트가 계산한다(`utils/date.js`·`utils/relevance.js`).
- 브랜드 로고는 `src/assets/logo.png` 에 있고 `Header`·`Landing`·`OnboardingWizard` 가 import 한다.
- 백엔드가 `onboarded` 를 안 내려주면(구버전) 위저드를 띄우지 않는 안전장치가 있다 — 온보딩은 명시적으로 `false` 일 때만 표시된다.
