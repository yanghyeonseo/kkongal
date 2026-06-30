import { useEffect, useState } from "react";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import AiRecommendBox from "./components/AiRecommendBox";
import NoticeCard from "./components/NoticeCard";
import SourceManageModal from "./components/SourceManageModal";
import { getMyInboxNotices } from "./api/inboxApi.js";
import { getNoticeSources } from "./api/sourceApi.js";
import "./App.css";

function App() {
  const [notices, setNotices] = useState([]);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isSourceModalOpen, setIsSourceModalOpen] = useState(false);

  useEffect(() => {
    async function loadInitialData() {
      try {
        const [noticeData, sourceData] = await Promise.all([
          getMyInboxNotices(),
          getNoticeSources(),
        ]);

        setNotices(noticeData);
        setSources(sourceData);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    }

    loadInitialData();
  }, []);

  const handleSaveSources = (selectedIds) => {
    setSources((prevSources) =>
      prevSources.map((source) => ({
        ...source,
        isSubscribed: selectedIds.includes(source.id),
      })),
    );
  };

  if (loading) {
    return <div className="loading">공지 목록을 불러오는 중...</div>;
  }

  return (
    <div className="app">
      <Header onOpenSources={() => setIsSourceModalOpen(true)} />

      <div className="layout">
        <Sidebar
          sources={sources}
          onOpenSources={() => setIsSourceModalOpen(true)}
        />

        <main className="main">
          <AiRecommendBox notices={notices} />

          <section className="noticeSection">
            <div className="noticeTitleRow">
              <h2>
                오늘 새 공지 <span>{notices.length}건</span>
              </h2>

              <div className="filterButtons">
                <button className="active">전체</button>
                <button>채용</button>
                <button>학교</button>
                <button>장학금</button>
              </div>
            </div>

            <div className="noticeList">
              {notices.map((notice) => (
                <NoticeCard key={notice.inboxNoticeId} notice={notice} />
              ))}
            </div>
          </section>
        </main>
      </div>

      {isSourceModalOpen && (
        <SourceManageModal
          sources={sources}
          onClose={() => setIsSourceModalOpen(false)}
          onSave={handleSaveSources}
        />
      )}
    </div>
  );
}

export default App;
