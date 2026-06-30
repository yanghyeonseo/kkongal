## [backend 실행 가이드]

1. 깃 클론

```
git clone https://github.com/yanghyeonseo/kkongal.git
cd kkongal/backend
git switch feature/backend_basic
```

2. 장고 키 세팅
   root directory에 .env 파일 생성 후, 키 입력 (https://djecrety.ir/)

```
# .env

SECRET_KEY='자기 장고 키'
DEBUG=True
```

3. 가상환경 생성 및 서버 실행

```
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

<br>

## [backend 추가된 폴더 구조]

```text
backend/
├─ kkongal/                  # Django project 설정
│  ├─ settings.py             # 앱 등록, DB, JWT, CORS 설정
│  └─ urls.py                 # 전체 API 라우팅
│
├─ account/                  # 유저/관심사
│  ├─ models.py               # User, Interest
│  ├─ views.py                # signup, signin, refresh, logout, interests API
│  ├─ serializers.py
│  └─ urls.py
│
├─ sources/                  # 사용자가 등록한 공지 사이트
│  ├─ models.py               # NoticeSource, SourceSubscription
│  ├─ views.py                # subscriptions API
│  ├─ serializers.py
│  └─ urls.py
│
├─ notices/                  # 공지 원본 및 사용자별 inbox 공지
│  ├─ models.py               # Notice, InboxNotice
│  ├─ views.py                # inbox notice API
│  ├─ serializers.py
│  └─ urls.py
│
├─ manage.py
├─ pyproject.toml
└─ uv.lock
```
<br>

## [프론트엔드용 API]

(Swagger에서 자세히 확인 가능: http://127.0.0.1:8000/api/schema/swagger-ui/)

로그인/유저 API

- POST /api/account/signup/
- POST /api/account/login/
- POST /api/account/refresh/
- POST /api/account/logout/

관심사 API

- GET /api/interests/
- POST /api/interests/
- PUT /api/interests/{id}/
- DELETE /api/interests/{id}/

등록된 공지 사이트 API

- GET /api/subscriptions/
- POST /api/subscriptions/
- DELETE /api/subscriptions/{id}/

공지 목록 API

- GET /api/notices/inbox/
- GET /api/notices/inbox/{id}/
