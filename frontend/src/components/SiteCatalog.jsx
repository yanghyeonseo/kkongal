import { useEffect, useMemo, useState } from "react";
import { Plus, Check, Loader2, RefreshCw } from "lucide-react";
import { getSourceCatalog } from "../api/sourceApi.js";
import SourceFavicon from "./SourceFavicon.jsx";

const CATEGORY_LABELS = {
  all: "전체",
  school: "학교",
  job: "채용",
  scholarship: "장학",
  activity: "대외활동",
  contest: "공모전",
  community: "커뮤니티",
  culture: "문화",
  etc: "기타",
};

/**
 * 지원 사이트 카탈로그 그리드.
 * - 카탈로그는 자체 로드(GET /api/sources/catalog/)하고, 카테고리 필터를 제공한다.
 * - 구독 여부(isSubscribed)와 토글 동작(onToggle)은 부모가 진리원본으로 제어한다.
 *   onToggle(item, nextSubscribed) => Promise
 */
function SiteCatalog({ isSubscribed, onToggle }) {
  const [catalog, setCatalog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeCat, setActiveCat] = useState("all");
  const [busyUrl, setBusyUrl] = useState(null);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getSourceCatalog();
      setCatalog(data);
    } catch (err) {
      setError(err.message || "지원 사이트 목록을 불러오지 못했어요.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const categories = useMemo(() => {
    const set = new Set(catalog.map((item) => item.category));
    return ["all", ...Array.from(set)];
  }, [catalog]);

  const visible = useMemo(() => {
    if (activeCat === "all") return catalog;
    return catalog.filter((item) => item.category === activeCat);
  }, [catalog, activeCat]);

  const handleToggle = async (item) => {
    const next = !isSubscribed(item);
    setBusyUrl(item.url);
    try {
      await onToggle(item, next);
    } finally {
      setBusyUrl(null);
    }
  };

  if (loading) {
    return (
      <div className="catalogGrid" aria-busy="true">
        {[0, 1, 2, 3].map((key) => (
          <div key={key} className="catalogItem">
            <div className="skeletonLine catalogLogo" />
            <div className="skeletonStack">
              <div className="skeletonLine w70" />
              <div className="skeletonLine w30" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="catalogEmpty">
        <p style={{ margin: "0 0 12px" }}>{error}</p>
        <button type="button" className="ghostButton" onClick={load}>
          <RefreshCw size={15} /> 다시 시도
        </button>
      </div>
    );
  }

  if (catalog.length === 0) {
    return <div className="catalogEmpty">지원하는 사이트가 아직 없어요.</div>;
  }

  return (
    <>
      <div className="catalogToolbar" role="tablist" aria-label="카테고리 필터">
        {categories.map((cat) => (
          <button
            key={cat}
            type="button"
            role="tab"
            aria-selected={activeCat === cat}
            className={`catalogFilter ${activeCat === cat ? "active" : ""}`}
            onClick={() => setActiveCat(cat)}
          >
            {CATEGORY_LABELS[cat] || cat}
          </button>
        ))}
      </div>

      <div className="catalogGrid">
        {visible.map((item) => {
          const subscribed = isSubscribed(item);
          const busy = busyUrl === item.url;
          return (
            <div
              key={item.url}
              className={`catalogItem ${subscribed ? "subscribed" : ""}`}
            >
              <SourceFavicon
                name={item.name}
                faviconUrl={item.faviconUrl}
                siteUrl={item.url}
                size={40}
                rounded="12px"
                className="catalogLogo"
              />
              <div className="catalogInfo">
                <strong>{item.name}</strong>
                <span className="catalogCat">
                  {CATEGORY_LABELS[item.category] || item.category}
                </span>
              </div>
              <button
                type="button"
                className={`catalogToggle ${subscribed ? "on" : ""}`}
                onClick={() => handleToggle(item)}
                disabled={busy}
                aria-pressed={subscribed}
                aria-label={
                  subscribed ? `${item.name} 구독 해제` : `${item.name} 구독`
                }
                title={subscribed ? "구독 중 · 눌러서 해제" : "구독하기"}
              >
                {busy ? (
                  <Loader2 size={16} className="spin" />
                ) : subscribed ? (
                  <Check size={16} />
                ) : (
                  <Plus size={16} />
                )}
              </button>
            </div>
          );
        })}
      </div>
    </>
  );
}

export default SiteCatalog;
