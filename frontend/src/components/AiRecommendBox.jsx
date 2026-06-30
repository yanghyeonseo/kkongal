function AiRecommendBox({ notices }) {
  const recommended = notices
    .filter((notice) => notice.relevanceScore >= 0.8)
    .slice(0, 3);

  return (
    <section className="aiBox">
      <div className="aiHeader">
        <div className="aiIcon">⚡</div>

        <div>
          <p>AI 추천</p>
          <h2>내 관심사에 맞는 새 공지 {recommended.length}건</h2>
        </div>
      </div>

      <div className="aiList">
        {recommended.map((notice, index) => (
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
            {notice.isNew && <b>NEW</b>}
            <span className="arrow">›</span>
          </a>
        ))}
      </div>
    </section>
  );
}

export default AiRecommendBox;
