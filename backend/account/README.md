# account — 사용자 계정·관심 조건·인증

## 개요

`account` 는 회원 계정과 인증, 그리고 AI 선별의 핵심 입력인 **관심 조건(Interest)** 을 담당한다. 인증은 SimpleJWT 기반이되, 프론트엔드가 쿠키 흐름으로 동작하도록 **쿠키에 담긴 `access_token` 도 읽는** 커스텀 인증(`CookieJWTAuthentication`)을 쓴다. 사용자는 회원가입 후 온보딩(관심사·알림 채널·사이트 등록)을 거치며, 그 완료 여부를 `User.onboarded` 로 관리한다. 이메일은 알림 발송의 수신자 식별에 쓰이므로 가입 시 필수이며 대소문자 무시 유니크로 검증한다.

## 구성

| 파일 | 역할 |
| --- | --- |
| `models.py` | `User`(AbstractUser 확장: `email`·`age`·`job`·`gender`·`onboarded`·`created_at`), `Interest`(`user_id`·`keyword`·`description`·`priority`·`created_at`) |
| `authentication.py` | `CookieJWTAuthentication` — `Authorization: Bearer` 헤더 우선, 없으면 `access_token` 쿠키. 만료/무효 토큰은 예외 대신 **비인증(None)** 으로 흘려보내 공개 엔드포인트를 막지 않는다 |
| `serializers.py` | `UserSerializer`(응답용, `password` write-only·`onboarded` read-only), `InterestSerializer` |
| `request_serializers.py` | 가입/로그인/토큰/로그아웃 입력 검증. `SignUpRequestSerializer` 가 이메일 형식·유니크, username 유니크, 비밀번호 강도(`AUTH_PASSWORD_VALIDATORS`)를 담당 |
| `views.py` | 인증·프로필·온보딩·관심사 API 뷰 |
| `urls.py` | `urlpatterns`(account 라우트)와 `interest_urlpatterns`(관심사 CRUD, 프로젝트 urlconf 가 `/api/interests/` 로 마운트) |

## 흐름 · 사용법

로그인/회원가입 성공 시 `set_token_on_response_cookie` 가 `access_token`·`refresh_token` 을 응답 쿠키로 내려주고, 이후 요청은 쿠키(또는 Bearer 헤더)로 인증된다. 프로젝트 기본 권한은 `IsAuthenticated`(fail-closed)이며, 공개 엔드포인트(가입·로그인·재발급·로그아웃·`me`·카탈로그 등)만 명시적으로 `AllowAny` 로 연다.

계정·인증 엔드포인트 (`/api/account/`):

| 메서드 · 경로 | 설명 |
| --- | --- |
| `POST /api/account/signup/` | 회원가입(성공 시 201 + 토큰 쿠키, 응답 user 에 `onboarded=false`) |
| `POST /api/account/signin/` | 로그인(username + password) |
| `POST /api/account/refresh/` | `refresh_token` 을 회전(rotation)해 새 access·refresh 발급, 이전 refresh 는 블랙리스트 |
| `POST /api/account/logout/` | refresh 토큰 블랙리스트 처리 + 쿠키 삭제 |
| `GET /api/account/me/` | 쿠키의 `access_token` 기준 현재 사용자 조회 |
| `POST /api/account/onboarding/complete/` | 온보딩 완료(`onboarded=True`) 표시 |

관심 조건 엔드포인트 (`/api/interests/`):

| 메서드 · 경로 | 설명 |
| --- | --- |
| `GET /api/interests/` | 관심 조건 목록(우선순위·최신순) |
| `POST /api/interests/` | 관심 조건 생성 |
| `PUT /api/interests/<id>/` | 관심 조건 수정 |
| `DELETE /api/interests/<id>/` | 관심 조건 삭제 |

## 유의사항

- **관심 조건은 AI 선별의 핵심 입력**이다. `keyword` + `description`(자연어) + `priority` 가 그대로 LLM 프롬프트에 실려(→ `ai/prompts.py`) 의미 기준 판단에 쓰인다. 관심 조건이 하나도 없는 사용자는 선별 대상에서 제외된다.
- 인증 실패를 **예외로 던지지 않는** 설계(`authentication.py`)는 브라우저에 남은 stale 토큰 때문에 로그인/회원가입까지 401 로 막히는 문제를 피하기 위한 의도된 선택이다.
- 토큰 쿠키는 **HttpOnly + SameSite=Lax + Secure(프로덕션)** 로 내려간다(`settings.AUTH_COOKIE_*`). 프론트는 토큰을 JS 로 읽지 않고 `credentials:"include"` 로 자동 전송되는 쿠키에 의존하며, 백엔드가 `access_token` 쿠키를 직접 읽어 인증한다.
- 로그인 실패는 사용자 존재 여부를 노출하지 않도록 **단일 401** 로 응답하고, 가입·로그인은 무차별 대입 완화를 위해 rate-limit(`THROTTLE_AUTH`, 기본 10/min)을 건다.
- `onboarded` 는 가입/수정 입력으로 바꿀 수 없고 **온보딩 완료 엔드포인트로만** 갱신된다.
