import { isToday } from "../utils/date.js";
import { Zap } from "lucide-react";

function AiRecommendBox({ notices, interests }) {
  const recommended = notices
    .filter((notice) => isToday(notice.publishedAt))
    .filter(
      (notice) =>
        notice.relevanceScore >= 0.8 || notice.matchedInterestTags?.length > 0,
    )
    .slice(0, 3);

  const interestSummary =
    interests.length > 0
      ? interests.map((interest) => interest.keyword).join(" / ")
      : "관심사";

  return (
    <section className="aiBox">
      <div className="aiHeader">
        <div className="aiIcon">
          <Zap size={22} strokeWidth={1.5} />
        </div>

        <div>
          <p>AI 추천</p>
          <h2>
            내 관심사({interestSummary})에 맞는 새 공지 {recommended.length}건
          </h2>
        </div>
      </div>

      <div className="aiList">
        {recommended.length === 0 ? (
          <div className="aiEmptyText">
            오늘 올라온 공지 중 관심사와 일치하는 추천 공지가 아직 없어요.
          </div>
        ) : (
          recommended.map((notice, index) => (
            <a
              key={notice.inboxNoticeId}
              className="aiRow"
              href={notice.url}
              target="_blank"
              rel="noreferrer"
            >
              <span className="rank">{index + 1}</span>
              <strong>{notice.title}</strong>
              <em>{notice.sourceDisplayName}</em>
              <b>NEW</b>
              <span className="arrow">›</span>
            </a>
          ))
        )}
      </div>
    </section>
  );
}

export default AiRecommendBox;
