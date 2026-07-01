const hoursAgo = (hours) =>
  new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();

const daysAgo = (days) =>
  new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

const daysAfter = (days) =>
  new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString();

export const mockInboxNotices = [
  {
    inboxNoticeId: 101,
    noticeId: 1,
    sourceId: 4,
    sourceName: "Naver_recruit",
    sourceDisplayName: "네이버 채용",
    category: "job",
    title: "Server Developer Internship 채용 오픈",
    description: "3개월 인턴십, 서울 근무",
    url: "https://recruit.navercorp.com/rcrt/list.do",
    publishedAt: hoursAgo(2),
    deadlineAt: daysAfter(14),

    relevanceScore: 0.94,
    matchedInterestTags: ["백엔드", "인턴", "서울"],
    reason:
      "등록한 관심사 '백엔드', '인턴', '서울'과 모두 관련 있습니다. 직무 설명에 서버 개발과 인턴십 조건이 포함되어 있습니다.",

    isRead: false,
    isSaved: false,
    isDeadlineSoon: false,
  },
  {
    inboxNoticeId: 102,
    noticeId: 2,
    sourceId: 5,
    sourceName: "Jobkorea_ai",
    sourceDisplayName: "잡코리아 AI 채용",
    category: "job",
    title: "AI 서비스 백엔드 신입 개발자 모집",
    description: "Spring Boot 기반 AI 서비스 개발",
    url: "https://www.jobkorea.co.kr/recruit/ai-jobs?pageNo=1&pageSize=100",
    publishedAt: hoursAgo(5),
    deadlineAt: daysAfter(5),

    relevanceScore: 0.9,
    matchedInterestTags: ["백엔드", "AI", "신입"],
    reason:
      "사용자의 백엔드 및 AI 관심사와 관련성이 높습니다. 공고에 Spring Boot와 AI 서비스 개발 키워드가 포함되어 있습니다.",

    isRead: false,
    isSaved: true,
    isDeadlineSoon: true,
  },
  {
    inboxNoticeId: 103,
    noticeId: 3,
    sourceId: 1,
    sourceName: "Snu_cse_notice",
    sourceDisplayName: "서울대 컴공 공지",
    category: "school",
    title: "2026 여름학기 학부 연구생 모집",
    description: "컴퓨터공학부 연구실별 학부 연구생 신청 안내",
    url: "https://cse.snu.ac.kr/community/notice",
    publishedAt: hoursAgo(7),
    deadlineAt: daysAfter(3),

    relevanceScore: 0.84,
    matchedInterestTags: ["컴퓨터공학", "연구생", "인턴"],
    reason:
      "사용자의 컴퓨터공학 및 인턴 관심사와 관련된 학부 연구생 모집 공지입니다.",

    isRead: false,
    isSaved: false,
    isDeadlineSoon: true,
  },
  {
    inboxNoticeId: 104,
    noticeId: 4,
    sourceId: 3,
    sourceName: "Saramin_hot100",
    sourceDisplayName: "사람인 HOT100",
    category: "job",
    title: "핀테크 스타트업 백엔드 개발자 채용",
    description: "Node.js, MySQL 기반 서비스 개발",
    url: "https://www.saramin.co.kr/zf_user/jobs/hot100",
    publishedAt: hoursAgo(10),
    deadlineAt: daysAfter(20),

    relevanceScore: 0.88,
    matchedInterestTags: ["백엔드", "핀테크"],
    reason: "사용자의 백엔드 관심사와 공고의 서버 개발 직무가 일치합니다.",

    isRead: true,
    isSaved: false,
    isDeadlineSoon: false,
  },
  {
    inboxNoticeId: 105,
    noticeId: 5,
    sourceId: 6,
    sourceName: "TheDreamKorea_scholarship",
    sourceDisplayName: "더드림코리아 장학금",
    category: "scholarship",
    title: "IT 전공 대학생 장학금 신청 안내",
    description: "컴퓨터공학 및 AI 분야 전공자 우대",
    url: "https://www.thedreamkorea.com/scholarships?tab=all",
    publishedAt: daysAgo(1),
    deadlineAt: daysAfter(6),

    relevanceScore: 0.82,
    matchedInterestTags: ["장학금", "IT", "AI"],
    reason:
      "사용자의 AI 및 컴퓨터공학 관심사와 장학금 선발 조건이 관련 있습니다.",

    isRead: false,
    isSaved: true,
    isDeadlineSoon: true,
  },
  {
    inboxNoticeId: 106,
    noticeId: 6,
    sourceId: 2,
    sourceName: "Snu_cba_notice",
    sourceDisplayName: "서울대 경영대 공지",
    category: "school",
    title: "2026학년도 교환학생 설명회 안내",
    description: "경영대학 국제교류 프로그램 설명회",
    url: "https://cba.snu.ac.kr/newsroom/notice?sc=y",
    publishedAt: daysAgo(2),
    deadlineAt: daysAfter(12),

    relevanceScore: 0.45,
    matchedInterestTags: [],
    reason: "",

    isRead: false,
    isSaved: false,
    isDeadlineSoon: false,
  },
  {
    inboxNoticeId: 107,
    noticeId: 7,
    sourceId: 7,
    sourceName: "TheDreamKorea_activity",
    sourceDisplayName: "더드림코리아 대외활동",
    category: "activity",
    title: "대학생 IT 서비스 기획 서포터즈 모집",
    description: "서비스 기획, 데이터 분석, 개발 협업 활동",
    url: "https://www.thedreamkorea.com/activities",
    publishedAt: daysAgo(3),
    deadlineAt: daysAfter(2),

    relevanceScore: 0.78,
    matchedInterestTags: ["IT", "서비스 기획"],
    reason: "사용자의 IT 관심사와 서비스 기획 활동 내용이 일부 관련 있습니다.",

    isRead: true,
    isSaved: false,
    isDeadlineSoon: true,
  },
  {
    inboxNoticeId: 108,
    noticeId: 8,
    sourceId: 8,
    sourceName: "TheDreamKorea_contest",
    sourceDisplayName: "더드림코리아 공모전",
    category: "contest",
    title: "AI 활용 서비스 아이디어 공모전",
    description: "생성형 AI를 활용한 서비스 아이디어 제출",
    url: "https://www.thedreamkorea.com/contests",
    publishedAt: daysAgo(4),
    deadlineAt: daysAfter(9),

    relevanceScore: 0.86,
    matchedInterestTags: ["AI", "서비스"],
    reason: "사용자의 AI 관심사와 공모전 주제가 직접적으로 관련되어 있습니다.",

    isRead: false,
    isSaved: false,
    isDeadlineSoon: false,
  },
  {
    inboxNoticeId: 109,
    noticeId: 9,
    sourceId: 9,
    sourceName: "Interpark_concert",
    sourceDisplayName: "인터파크 티켓 콘서트",
    category: "culture",
    title: "인디밴드 라이브 콘서트 티켓 오픈",
    description: "서울 공연, 선착순 예매 진행",
    url: "https://tickets.interpark.com/contents/genre/concert",
    publishedAt: daysAgo(5),
    deadlineAt: daysAfter(30),

    relevanceScore: 0.32,
    matchedInterestTags: [],
    reason: "",

    isRead: false,
    isSaved: true,
    isDeadlineSoon: false,
  },
  {
    inboxNoticeId: 110,
    noticeId: 10,
    sourceId: 10,
    sourceName: "Naver_cafe_notice",
    sourceDisplayName: "네이버 카페 공지",
    category: "community",
    title: "개발 스터디 7월 모집 공지",
    description: "백엔드, 알고리즘, 프로젝트 스터디원 모집",
    url: "https://cafe.naver.com/f-e/cafes/31723403/menus/2",
    publishedAt: daysAgo(6),
    deadlineAt: daysAfter(4),

    relevanceScore: 0.8,
    matchedInterestTags: ["백엔드", "스터디"],
    reason: "사용자의 백엔드 관심사와 개발 스터디 모집 내용이 관련 있습니다.",

    isRead: false,
    isSaved: false,
    isDeadlineSoon: true,
  },
];
