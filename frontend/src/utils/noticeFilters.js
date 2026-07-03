import { isAiMatched } from "./relevance.js";

// 관심사 칩 매칭: 선택한 키워드 중 하나라도 matched_keywords 와 겹치면 통과(OR).
function matchesInterests(notice, activeInterests) {
  if (activeInterests.length === 0) return true;
  const tags = (notice.matchedInterestTags || []).map((tag) => tag.toLowerCase());
  return activeInterests.some((keyword) =>
    tags.some((tag) => tag.includes(keyword) || keyword.includes(tag)),
  );
}

function matchesSearch(notice, query) {
  if (!query) return true;
  const haystack = [
    notice.title,
    notice.sourceDisplayName,
    notice.description,
    ...(notice.matchedInterestTags || []),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

/**
 * 뷰/카테고리/관심사/검색 조건으로 공지를 거른다.
 * `base` 는 호출부에서 이미 소스 범위를 적용한 목록이다.
 */
export function filterNotices(base, { view, category, interests, query }) {
  const activeInterests = interests.map((keyword) => keyword.toLowerCase());
  const normalizedQuery = query.trim().toLowerCase();

  return base.filter((notice) => {
    if (view === "ai" && !isAiMatched(notice)) return false;
    if (view === "saved" && !notice.isSaved) return false;
    if (category === "deadline" && !notice.isDeadlineSoon) return false;
    if (category === "expired" && !notice.isExpired) return false;
    if (!matchesInterests(notice, activeInterests)) return false;
    if (!matchesSearch(notice, normalizedQuery)) return false;
    return true;
  });
}
