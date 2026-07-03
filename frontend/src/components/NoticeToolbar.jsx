const VIEW_TITLES = {
  all: "전체 공지",
  ai: "AI 추천 공지",
  saved: "저장한 공지",
};

const CATEGORY_FILTERS = [
  { id: "all", label: "전체" },
  { id: "deadline", label: "마감임박" },
  { id: "expired", label: "마감" },
];

// 공지 섹션 상단: 뷰 제목·건수, 마감 카테고리 필터, 관심사 칩 필터.
function NoticeToolbar({
  view,
  count,
  selectedCategory,
  onSelectCategory,
  interests,
  selectedInterests,
  onToggleInterest,
  onClearInterests,
}) {
  return (
    <>
      <div className="noticeTitleRow">
        <div>
          <p className="sectionEyebrow">맞춤 공지함</p>
          <h2>
            {VIEW_TITLES[view]} <span>{count}</span>건
          </h2>
        </div>

        <div className="filterButtons">
          {CATEGORY_FILTERS.map((category) => (
            <button
              key={category.id}
              className={selectedCategory === category.id ? "active" : ""}
              aria-pressed={selectedCategory === category.id}
              onClick={() => onSelectCategory(category.id)}
            >
              {category.label}
            </button>
          ))}
        </div>
      </div>

      {interests.length > 0 && (
        <div className="interestFilterRow">
          <span className="interestFilterLabel">관심사</span>
          <div className="interestFilterChips">
            {interests.map((interest) => {
              const active = selectedInterests.includes(interest.keyword);
              return (
                <button
                  key={interest.id}
                  type="button"
                  className={`interestFilterChip ${active ? "active" : ""}`}
                  aria-pressed={active}
                  onClick={() => onToggleInterest(interest.keyword)}
                >
                  {interest.keyword}
                </button>
              );
            })}
            {selectedInterests.length > 0 && (
              <button
                type="button"
                className="interestFilterClear"
                onClick={onClearInterests}
              >
                초기화
              </button>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default NoticeToolbar;
