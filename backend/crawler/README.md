## [crawler 역할]

`crawler` 앱은 외부 공지 사이트를 크롤링해서 기존 백엔드 모델에 저장하는 역할

저장 흐름

```text
외부 사이트
→ crawler.scrapers
→ RawNotice
→ sources.NoticeSource
→ notices.Notice
→ notices.InboxNotice
```

프론트엔드가 직접 `crawler`를 호출하는 구조는 아님
크롤링은 서버 내부 작업이고, 프론트엔드는 `notices` API를 통해 저장된 공지를 조회

<br>

## [crawler 추가된 폴더 구조]

```text
crawler/
├─ config/
│  └─ sites.json                     # 크롤링 대상 사이트 설정
│
├─ scrapers/                         # 사이트별 크롤러
│  ├─ snu_cse_notice.py
│  ├─ snu_cba_notice.py
│  ├─ saramin_hot100.py
│  ├─ naver_recruit.py
│  ├─ jobkorea_ai.py
│  ├─ naver_cafe_notice.py
│  ├─ thedream_common.py             # 더드림코리아 공통 Supabase 조회/변환
│  ├─ thedream_scholarships.py
│  ├─ thedream_activities.py
│  ├─ thedream_contests.py
│  └─ interpark_concert.py
│
├─ management/
│  └─ commands/
│     └─ crawl_notices.py            # python manage.py crawl_notices
│
├─ schemas.py                        # RawNotice, CrawlReport
├─ service.py                        # 크롤링 실행 진입점
├─ repository.py                     # RawNotice를 Django ORM에 저장
├─ matcher.py                        # 관심사 키워드 기반 InboxNotice 생성
├─ fetcher.py                        # httpx 클라이언트 설정
└─ config_loader.py                  # sites.json 로더
```

기존 백엔드 파일에서 아래 파일들도 함께 수정

```text
backend/requirements.txt     # 크롤링 라이브러리 추가
backend/pyproject.toml       # uv 의존성 추가
backend/uv.lock              # uv lock 갱신
backend/kkongal/settings.py  # crawler 앱 등록
```

추가된 주요 라이브러리:

```text
httpx
beautifulsoup4
lxml
pydantic
python-dateutil
```

<br>

## [현재 등록된 크롤링 소스]

`crawler/config/sites.json`에 지금 등록된 소스

```text
snu_cse_notice
snu_cba_notice
saramin_hot100
naver_recruit
jobkorea_ai
naver_cafe_notice
thedream_scholarships
thedream_activities
thedream_contests
interpark_concert
```

<br>

<br>

## [크롤링 직접 확인 방법]

`backend/README.md`의 백엔드 실행 가이드를 먼저 실행

### 1. Django 설정 확인

```bash
uv run python manage.py check
```

정상적인 결과

```text
System check identified no issues
```

### 2. DB 저장 없이 미리보기

(ex) 서울대 컴공 공지 확인

```bash
uv run python manage.py crawl_notices --source snu_cse_notice --preview --limit 3
```

JSON 배열이 출력되면 크롤러 import와 실제 요청이 성공한 것

Windows 터미널 환경에 따라 한글이 `\uac00` 같은 유니코드 escape 형태로 보임에 주의

### 3. DB에 저장하기

아래 명령은 실제로 로컬 DB의 `NoticeSource`, `Notice` 테이블에 데이터를 저장

```bash
uv run python manage.py crawl_notices --source snu_cse_notice --no-match
```

`--no-match`는 관심사 매칭과 `InboxNotice` 생성을 잠시 끄는 옵션으로
크롤링/저장만 확인할 때 사용

성공 예시:

```text
snu_cse_notice: fetched=20, inserted=20, duplicates=0, errors=0
```

같은 명령을 다시 실행하면 이미 저장된 공지는 중복으로 처리

```text
snu_cse_notice: fetched=20, inserted=0, duplicates=20, errors=0
```

### 4. 저장 결과 확인

```bash
uv run python manage.py shell -c "from sources.models import NoticeSource; from notices.models import Notice; print(NoticeSource.objects.count()); print(Notice.objects.count())"
```

<br>

## [실행 방법]

`backend/README.md`의 백엔드 실행 가이드를 먼저 실행

```bash
uv run python manage.py crawl_notices [옵션]
```

주요 옵션:

```text
--source <source_id>  특정 소스만 크롤링
--preview             DB 저장 없이 결과만 출력
--limit <number>      preview 출력 개수
--no-match            InboxNotice 관심사 매칭 생략
```

예시:

```bash
uv run python manage.py crawl_notices --source snu_cse_notice --preview --limit 5
uv run python manage.py crawl_notices --source snu_cba_notice --no-match
uv run python manage.py crawl_notices --source thedream_scholarships --preview --limit 3
uv run python manage.py crawl_notices --source interpark_concert --preview --limit 3
```

`--source`를 생략하면 `sites.json`의 enabled 소스를 순서대로 모두 실행

<br>

## [주의사항]

1. `--source` 없이 실행하면 여러 외부 사이트에 연속으로 요청하기 때문에, 테스트할 때는 `--source`를 붙여서 한 사이트씩 확인하는 것을 권장

2. `crawler/fetcher.py`에는 현재 개발 환경 테스트를 위해 `verify=False`, `trust_env=False`가 들어가 있는데, 로컬 Windows 환경에서 SSL 검증 중 끊기는 문제가 있어 넣은 설정으로 배포 전에는 설정값으로 분리하거나 다시 확인 필요

3. 현재 매칭 로직은 `Interest.keyword`가 공지 제목/본문에 포함되는지 보는 단순 키워드 매칭으로, 추후 AI 선별 로직으로 `matcher.py`를 교체하거나 확장해야 함

4. 현재 InboxNotice 매칭은 새 Notice가 insert될 때만 실행, 즉, 이미 DB에 저장된 공지에 대해 나중에 사용자가 관심사/구독을 추가하면 자동으로 과거 공지까지 inbox에 들어가지는 않는데, 이 부분도 선별 로직을 변경할 때 고려할 수 있을 것 같음

5. `NoticeSource`는 현재 URL 기준으로 생성되므로 `snu_cse_notice` 같은 고정 식별자가 DB 모델에 따로 저장되지는 않기 때문에 장기적으로는 `source_key` 또는 `slug` 필드를 추가하는 것이 더 안정적일수도 있다고 함

6. 현재 사이트들은 어느 정도 잘 나오는 것을 확인했지만, 사이트 구조가 바뀌면 각 스크래퍼의 파싱 로직을 다시 확인해야 하고, 정적 HTML만으로 크롤링되지 않는 경우도 고민해봐야 할 수 있음, 또 크롤링 결과의 날짜가 파싱되지 않으면 `published_at`은 `null`로 저장되는데, 날짜 파싱은 사이트별로 보완이 필요할 수 있음

<br>

## [AI / 알림 연동 방식]

AI API 연동과 메일/슬랙/카카오톡 알림톡은 `crawler` 안에 직접 넣지 않고, 별도 앱인 `ai`, `alert`에서 진행하는 것을 추천

```text
crawler
→ notices.Notice 저장
→ matcher.py에서 1차 InboxNotice 생성
→ ai 앱에서 Notice/InboxNotice를 읽고 relevance_score, reason 보완
→ alert 앱에서 새 InboxNotice 또는 안 읽은 InboxNotice를 발송
```

구현할 때는 `crawler.repository.DjangoNoticeRepository.insert_many()`가 새 공지를 저장한 뒤 `matcher.match_notice_to_subscribers()`를 호출하는 지점이 있는데, 나중에 AI를 붙이면 이 단순 키워드 매칭을 AI 기반 함수로 바꾸거나, 크롤링이 끝난 뒤 `Notice` 목록을 읽어 `InboxNotice.relevance_score`, `reason`, `matched_keywords`를 업데이트하는 별도 작업으로 분리하는 것을 추천

알림은 크롤러 실행 중 바로 보내기보다는, `alert` 앱에서 `InboxNotice.objects.filter(is_read=False, ...)`처럼 발송 대상을 조회해서 보내는 방식이 안전, 이렇게 하면 크롤링 실패/재시도와 알림 중복 발송을 분리해서 관리 가능

<br>

## [기존 crawler (by 양현서)에서 유지/변경한 부분]

기존 crawler 폴더에서 살린 부분은 사이트별 스크래퍼를 따로 두는 구조, `sites.json`으로 크롤링 대상을 관리하는 방식, 그리고 크롤링 결과를 `RawNotice`라는 공통 형태로 맞추는 흐름

백엔드에 맞춰 바꾼 부분은 `crawler`를 Django 앱으로 등록한 것, `python manage.py crawl_notices` 명령어로 실행하게 한 것, `RawNotice`를 실제 `NoticeSource`, `Notice` 모델에 저장하는 `repository.py`를 추가한 것, 그리고 관심사 키워드 기반으로 `InboxNotice`를 만드는 `matcher.py`를 붙인 것

또한 사람인 사이트의 경우 일부 상세 페이지가 느리거나 실패하면 전체 크롤링이 멈추는 현상이 있어 약간 수정함 - 일부 상세 조회가 실패해도 요약만 쓰고 넘어가 목록 전체는 살아남게 수정

<br>

## [새로 추가한 사이트]

더드림코리아 3개 목록은 같은 서비스를 사용하므로 프론트엔드가 사용하는 공개 Supabase REST 응답을 조회하고, `thedream_common.py`에 공통 조회/변환 코드를 두었음. 장학금/대외활동/공모전 파일은 각각 테이블과 필터만 다르게 지정해 놓은 상태

```text
thedream_scholarships  scholarships 테이블
thedream_activities    activities 테이블 + type=activity
thedream_contests      activities 테이블 + type=contest
```

인터파크 티켓은 더드림코리아와 다르게 Supabase API가 아니라 페이지 HTML 안의 Next.js 초기 데이터에서 공연 정보를 읽음, `interpark_concert.py`는 별도 스크래퍼로 분리
콘서트가 아닌 이벤트성 항목이 섞이지 않도록 링크 기준 필터를 추가

<br>
