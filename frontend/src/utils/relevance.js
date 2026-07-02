// AI 추천으로 강조 표시할 관련도 임계값(백엔드 inbox 편입 임계값 0.5보다 높게 잡아 "강한 추천"만 강조).
export const AI_HIGH_RELEVANCE = 0.8;

// AI 매치로 볼지 여부: 높은 관련도이거나 매칭된 관심 태그가 있을 때.
export function isAiMatched(notice) {
  if (!notice) return false;
  return (
    notice.relevanceScore >= AI_HIGH_RELEVANCE ||
    (notice.matchedInterestTags && notice.matchedInterestTags.length > 0)
  );
}

// 0~1 관련도를 퍼센트 문자열로.
export function formatRelevance(score) {
  const value = Number(score) || 0;
  return `${Math.round(value * 100)}%`;
}

// 관련도 구간(색상 구분용).
export function relevanceTier(score) {
  const value = Number(score) || 0;
  if (value >= AI_HIGH_RELEVANCE) return "high";
  if (value >= 0.6) return "mid";
  return "low";
}
