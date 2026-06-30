import { useEffect, useState } from "react";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import AiRecommendBox from "./components/AiRecommendBox";
import NoticeCard from "./components/NoticeCard";
import { getMyInboxNotices } from "./api/inboxApi";
import "./App.css";

function App() {
  const [notices, setNotices] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadNotices() {
      try {
        const data = await getMyInboxNotices();
        setNotices(data);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    }

    loadNotices();
  }, []);

  if (loading) {
    return <div className="loading">공지 목록을 불러오는 중...</div>;
  }

  return (
    <div className="app">
      <Header />

      <div className="layout">
        <Sidebar />

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
    </div>
  );
}

export default App;
