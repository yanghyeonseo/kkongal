// 백엔드 inbox 편입 임계값(0.5)보다 높게 잡아 "강한 추천"만 강조한다.
const AI_HIGH_RELEVANCE = 0.8;

// AI 매치 여부는 백엔드가 계산한 is_recommended 를 그대로 따른다(임계값 로직은 백엔드 소유).
export function isAiMatched(notice) {
  return !!(notice && notice.isRecommended);
}

// 관련도 구간(색상 tier 구분용).
export function relevanceTier(score) {
  const value = Number(score) || 0;
  if (value >= AI_HIGH_RELEVANCE) return "high";
  if (value >= 0.6) return "mid";
  return "low";
}
