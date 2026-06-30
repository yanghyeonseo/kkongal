# 꽁알꽁알(Kkongal)

> 맞춤 공지 알리미 — 흩어진 공지를 한곳에서, AI가 필요한 것만 골라줍니다.

여러 사이트(채용 플랫폼, 학교·학부 공지, 관심 기업 채용 페이지 등)를 매일 따로 확인하는 **탐색 비용**을 줄여주는 웹 서비스입니다. 사용자가 관심 있는 사이트의 URL과 주제를 등록하면, 각 사이트의 공지 변화를 자동으로 감지·수집하고, LLM이 사용자의 관심사·조건에 맞는 공지만 선별해 하나의 대시보드로 모아 보여줍니다.

초기 구상과 세부 기획은 [IR Deck](docs/IR_Deck.pdf)에서, 서비스 소개는 [100초 피칭 영상](https://youtu.be/MK0nMy_avfU)에서 확인할 수 있습니다.

## 링크

- **배포 URL**: https://kkongal.cloud
- **프론트엔드 데모 (Figma)**: https://stung-arrow-75733307.figma.site
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

## 팀

| 이름   | GitHub                                           | 역할                                       |
| ------ | ------------------------------------------------ | ------------------------------------------ |
| 양현서 | [@yanghyeonseo](https://github.com/yanghyeonseo) | AI 선별·알림 기능 / 프론트·백엔드 지원     |
| 서지안 | [@Seo-Jian](https://github.com/Seo-Jian)         | 프론트엔드 (대시보드·사이트 등록 UI)       |
| 윤지후 | [@jeehooy2](https://github.com/jeehooy2)         | 백엔드 (크롤링·수집 파이프라인, 서버 로직) |
| 배진규 | [@r2rboss1](https://github.com/r2rboss1)         | 백엔드 (크롤링·수집 파이프라인, 서버 로직) |
