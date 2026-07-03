// 백엔드 inbox 편입 임계값(0.5)보다 높게 잡아 "강한 추천"만 강조한다.
const AI_HIGH_RELEVANCE = 0.8;

// 높은 관련도이거나 매칭된 관심 태그가 있으면 AI 매치로 본다.
export function isAiMatched(notice) {
  if (!notice) return false;
  return (
    notice.relevanceScore >= AI_HIGH_RELEVANCE ||
    (notice.matchedInterestTags && notice.matchedInterestTags.length > 0)
  );
}

// 관련도 구간(색상 tier 구분용).
export function relevanceTier(score) {
  const value = Number(score) || 0;
  if (value >= AI_HIGH_RELEVANCE) return "high";
  if (value >= 0.6) return "mid";
  return "low";
}
