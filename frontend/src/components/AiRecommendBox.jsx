import { Sparkles, ArrowUpRight } from "lucide-react";
import { isToday } from "../utils/date.js";
import { isAiMatched, formatRelevance, relevanceTier } from "../utils/relevance.js";

function AiRecommendBox({ notices, interests, onOpenNotice }) {
  const recommended = notices
    .filter((notice) => isToday(notice.publishedAt))
    .filter(isAiMatched)
    .sort((a, b) => (b.relevanceScore || 0) - (a.relevanceScore || 0))
    .slice(0, 3);

  const keywords = interests.map((interest) => interest.keyword).filter(Boolean);
  const interestSummary =
    keywords.length > 0
      ? keywords.slice(0, 4).join(" · ") + (keywords.length > 4 ? " 외" : "")
      : "관심사 미설정";

  return (
    <section className="aiBox">
      <div className="aiHeader">
        <div className="aiIcon">
          <Sparkles size={22} strokeWidth={2} />
        </div>

        <div className="aiHeaderText">
          <p>AI 추천</p>
          <h2>오늘 당신에게 꼭 맞는 공지 {recommended.length}건</h2>
          <span className="aiInterestSummary">기준 관심사 · {interestSummary}</span>
        </div>
      </div>

      <div className="aiList">
        {recommended.length === 0 ? (
          <div className="aiEmptyText">
            오늘 올라온 공지 중 관심사와 강하게 일치하는 추천 공지가 아직 없어요.
            관심사를 추가하면 더 정확해져요.
          </div>
        ) : (
          recommended.map((notice, index) => {
            const tier = relevanceTier(notice.relevanceScore);
            return (
              <button
                type="button"
                key={notice.inboxNoticeId}
                className="aiRow"
                onClick={() => onOpenNotice(notice)}
              >
                <span className={`rank tier-${tier}`}>{index + 1}</span>

                <div className="aiRowMain">
                  <strong>{notice.title}</strong>
                  <span className="aiRowReason">
                    {notice.sourceDisplayName}
                    {notice.reason ? ` · ${notice.reason}` : ""}
                  </span>
                </div>

                <span className={`aiRowScore tier-${tier}`}>
                  {formatRelevance(notice.relevanceScore)}
                </span>
                <ArrowUpRight size={18} className="aiRowArrow" aria-hidden="true" />
              </button>
            );
          })
        )}
      </div>
    </section>
  );
}

export default AiRecommendBox;
