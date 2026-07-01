#실행 방법

git clone https://github.com/yanghyeonseo/kkongal.git
cd kkongal
git fetch origin
git switch feature/frontend-dashboard
cd frontend
npm install
npm install lucide-react
npm run dev
순으로 하시면 됩니다

주요 기능
맞춤 공지 대시보드

- 로그인한 사용자의 공지 목록을 표시합니다.
- 오늘 올라온 새 공지 개수를 표시합니다.
- 공지 카드 제목을 클릭하면 원문 페이지가 새 탭으로 열립니다.
- 클릭한 공지는 프론트 상태에서 읽음 처리됩니다.
- 읽은 공지는 제목 색상이 보라색으로 표시됩니다.

AI 추천 공지

- 사용자 관심사와 관련 있는 공지를 AI 추천 박스에 표시합니다.
- relevance_score 또는 matched_keywords 기준으로 AI 매치 여부를 판단합니다.
- AI 매치 태그를 클릭하면 추천 이유가 표시됩니다.
- 매칭된 관심사 키워드가 태그 형태로 표시됩니다.

공지 필터

상단 필터

- 전체
- 마감임박

사이드바 필터

- 전체
- AI 추천
- 저장됨
- 내 사이트별 켜기/끄기

저장 기능

- 공지 카드의 저장 버튼을 클릭하면 저장 상태가 변경됩니다.
- 저장된 공지는 저장됨 탭에서 확인할 수 있습니다.
- 저장 해제도 같은 버튼으로 처리합니다.
- 저장과 해제는 inboxNoticeId 기준으로 처리합니다.

관심사 설정

- 사용자 관심사 태그를 추가할 수 있습니다.
- 사용자 관심사 태그를 삭제할 수 있습니다.
- 관심사 저장 버튼을 통해 변경 내용을 저장합니다.
- 관심사는 AI 추천 문구와 AI 매칭 조건 표시에 사용됩니다.

사이트 등록

- 사용자가 공지를 받고 싶은 사이트 URL을 등록합니다.
- 사이트 등록 모달에서는 URL만 입력합니다.
- 사이트 이름은 프론트에서 직접 전송하지 않습니다.

사용 기술

- React
- Vite
- CSS
- lucide-react

폴더 구조

- frontend/
- frontend/src/
- frontend/src/api/
- frontend/src/api/client.js
- frontend/src/api/authApi.js
- frontend/src/api/inboxApi.js
- frontend/src/api/sourceApi.js
- frontend/src/api/interestApi.js
- frontend/src/components/
- frontend/src/components/Header.jsx
- frontend/src/components/Sidebar.jsx
- frontend/src/components/AiRecommendBox.jsx
- frontend/src/components/NoticeCard.jsx
- frontend/src/components/SiteRegisterModal.jsx
- frontend/src/components/InterestSettingModal.jsx
- frontend/src/components/AuthModal.jsx
- frontend/src/data/
- frontend/src/data/mockInboxNotices.js
- frontend/src/data/mockSources.js
- frontend/src/data/mockInterests.js
- frontend/src/utils/
- frontend/src/utils/date.js
- frontend/src/App.jsx
- frontend/src/App.css
- frontend/src/index.css

프론트에서 사용하는 공지 데이터 형태

백엔드 응답은 src/api/inboxApi.js에서 화면용 데이터로 변환해서 사용합니다.

- inboxNoticeId: inbox 공지 id
- noticeId: 원본 공지 id
- sourceId: 공지 출처 id
- sourceName: 공지 출처 이름
- sourceDisplayName: 화면에 표시할 공지 출처 이름
- title: 공지 제목
- description: 공지 내용 요약
- url: 공지 원문 주소
- publishedAt: 공지 게시일
- deadlineAt: 마감일
- relevanceScore: AI 관련도 점수
- matchedKeywords: 매칭 키워드 목록
- matchedInterestTags: 화면에 표시할 매칭 관심사 태그 목록
- reason: AI 추천 이유
- isRead: 읽음 여부
- isSaved: 저장 여부
- isDeadlineSoon: 마감임박 여부

데이터 처리 기준
NEW 표시

- publishedAt이 오늘 날짜이면 카드에 NEW 태그를 표시합니다.
- publishedAt이 없으면 NEW 태그를 표시하지 않습니다.

D-day 표시

- deadlineAt을 기준으로 프론트에서 D-day를 계산합니다.
- 마감일이 있으면 D-5, D-DAY, 마감 형태로 표시합니다.
- 마감일이 없으면 D-day를 표시하지 않습니다.

마감임박 표시

- 오늘 기준 마감일까지 7일 이내이면 마감임박 태그를 표시합니다.
- D-7부터 D-DAY까지 마감임박으로 표시합니다.
- 이미 마감된 공지는 마감임박으로 표시하지 않습니다.
- 마감일이 없는 공지는 마감임박으로 표시하지 않습니다.

AI 매치 표시

아래 조건 중 하나라도 만족하면 AI 매치 공지로 표시합니다.

- relevanceScore가 0.8 이상인 경우
- matchedInterestTags가 1개 이상 존재하는 경우

AI 매치 공지 처리 방식

- 카드에 AI 매치 태그가 표시됩니다.
- AI 매치 태그를 클릭하면 추천 이유가 열립니다.
- 번개 아이콘을 클릭해도 추천 이유가 열립니다.
- 추천 이유 영역에는 reason 값이 표시됩니다.
- 매칭 키워드는 태그 형태로 표시됩니다.

저장됨 표시

- isSaved가 true이면 저장된 공지로 표시합니다.
- isSaved가 false이면 저장되지 않은 공지로 표시합니다.
- 저장 버튼을 다시 클릭하면 저장 상태가 반대로 바뀝니다.
- 저장됨 탭에서는 isSaved가 true인 공지만 표시합니다.

읽음 표시

- 공지 제목을 클릭하면 원문 페이지가 새 탭으로 열립니다.
- 동시에 해당 공지는 프론트 상태에서 읽음 처리됩니다.
- 읽은 공지는 제목 색상을 보라색으로 표시합니다.
- 읽음 처리는 현재 백엔드 API를 호출하지 않고 프론트 상태에서만 처리합니다.

실제 API 연결 시 프론트 작업 내용

- src/api/client.js를 실제 API 요청 코드로 교체합니다.
- src/api/authApi.js를 실제 로그인, 회원가입, 현재 유저 조회 코드로 교체합니다.
- src/api/inboxApi.js를 실제 공지 목록, 저장 API 기준 코드로 교체합니다.
- src/api/sourceApi.js를 실제 사이트 등록, 조회 API 기준 코드로 교체합니다.
- src/api/interestApi.js를 실제 관심사 API 기준 코드로 교체합니다.
- App.jsx에서 MOCK_USER를 제거합니다.
- App.jsx에서 mock 데이터 import를 제거합니다.
- 앱 시작 시 현재 로그인 유저를 조회합니다.
- 로그인한 유저가 있을 때만 공지, 사이트, 관심사 데이터를 불러옵니다.
- 로그인은 username/password 기준으로 요청합니다.
- 회원가입은 username/email/password/age/job/gender 기준으로 요청합니다.
- 공지 저장과 해제는 inboxNoticeId 기준으로 처리합니다.
- 사이트 등록은 URL만 전송합니다.
- 관심사 저장은 관심사 배열을 기준으로 처리합니다.
- 상단 필터는 전체와 마감임박만 사용합니다.

API 연동 시 사용하는 프론트 파일
client.js

- 모든 API 요청의 공통 fetch 함수를 관리합니다.
- API 기본 주소를 관리합니다.
- credentials include 설정을 포함합니다.
- 요청 실패 시 에러 메시지를 처리합니다.

authApi.js

- 현재 로그인 유저 조회를 담당합니다.
- 로그인 요청을 담당합니다.
- 회원가입 요청을 담당합니다.
- 로그아웃 요청을 담당합니다.

inboxApi.js

- 공지 목록 조회를 담당합니다.
- 백엔드 공지 응답을 화면용 데이터로 변환합니다.
- matched_keywords를 배열로 변환합니다.
- deadline_at을 기준으로 마감임박 여부를 계산합니다.
- 저장과 저장 해제 요청을 담당합니다.

sourceApi.js

- 구독 사이트 목록 조회를 담당합니다.
- 사이트 URL 등록을 담당합니다.
- 구독 사이트 삭제를 담당합니다.

interestApi.js

- 관심사 목록 조회를 담당합니다.
- 관심사 추가를 담당합니다.
- 관심사 수정과 삭제를 담당합니다.
- 관심사 저장 시 기존 관심사와 새 관심사를 비교해 반영합니다.

연동 후 테스트 순서

- 프론트 실행
- 회원가입 테스트
- 로그인 테스트
- 로그인 후 공지 목록 표시 확인
- AI 추천 박스 표시 확인
- 공지 카드 클릭 후 원문 이동 확인
- 읽은 공지 제목 보라색 표시 확인
- 저장 버튼 클릭 확인
- 저장됨 탭 확인
- 사이트 URL 등록 확인
- 관심사 추가 확인
- 관심사 삭제 확인
- 관심사 저장 확인
- 전체 필터 확인
- 마감임박 필터 확인

브라우저에서 확인할 요청

새로고침 시 확인할 요청

- GET /api/account/me/

로그인 시 확인할 요청

- POST /api/account/signin/

로그인 후 확인할 요청

- GET /api/notices/inbox/
- GET /api/subscriptions/
- GET /api/interests/

저장 버튼 클릭 시 확인할 요청

- PATCH /api/notices/inbox/{inbox_notice_id}/save/

사이트 등록 시 확인할 요청

- POST /api/subscriptions/

관심사 저장 시 확인할 요청

- GET /api/interests/
- POST /api/interests/
- DELETE /api/interests/{interest_id}/

오류 확인 기준
화면이 비어 있는 경우

- 로그인 상태인지 확인합니다.
- 공지 목록 요청이 성공했는지 확인합니다.
- 응답 데이터가 배열인지 확인합니다.
- notice 객체가 응답 안에 있는지 확인합니다.
- notice.source 값이 비어 있지 않은지 확인합니다.

로그인 후에도 데이터가 안 뜨는 경우

- 현재 유저 조회가 성공하는지 확인합니다.
- 프론트 요청에 쿠키가 포함되는지 확인합니다.
- 브라우저 Network 탭에서 요청 실패 여부를 확인합니다.
- GET /api/account/me/ 요청이 성공하는지 확인합니다.

저장 버튼이 실패하는 경우

- 저장 요청에 noticeId가 아니라 inboxNoticeId를 사용하는지 확인합니다.
- 요청 body에 is_saved 값이 포함되는지 확인합니다.
- PATCH 요청 주소가 /api/notices/inbox/{inbox_notice_id}/save/ 형태인지 확인합니다.

사이트 등록이 실패하는 경우

- 사이트 등록 요청에 URL만 보내는지 확인합니다.
- URL이 빈 값이 아닌지 확인합니다.
- 요청 body에 name이나 sourceId를 보내지 않는지 확인합니다.

공지 클릭 이동이 이상한 경우

- 공지 데이터의 url 값이 올바른 원문 주소인지 확인합니다.
- url 값이 상대경로가 아닌지 확인합니다.
- 새 탭 차단 여부를 확인합니다.

AI 추천 공지가 안 뜨는 경우

- relevanceScore 값이 0.8 이상인지 확인합니다.
- matchedInterestTags 배열에 값이 있는지 확인합니다.
- matched_keywords가 정상적으로 파싱되는지 확인합니다.
- source filter에 의해 제외된 공지가 아닌지 확인합니다.

마감임박 필터가 안 되는 경우

- deadlineAt 값이 있는지 확인합니다.
- deadlineAt 값이 날짜 형식인지 확인합니다.
- 오늘 기준 7일 이내인지 확인합니다.
- 이미 마감된 공지인지 확인합니다.
