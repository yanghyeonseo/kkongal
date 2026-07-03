import { useEffect, useRef, useState } from "react";
import { Globe, Sparkles, Bookmark, Plus, RefreshCw } from "lucide-react";
import SourceFavicon from "./SourceFavicon.jsx";

function Sidebar({
  sources,
  selectedView,
  onChangeView,
  onOpenSiteRegister,
  aiCount,
  savedCount,
  activeSourceIds,
  onToggleSource,
  syncingSourceIds = [],
  onSyncSource,
  onSyncAll,
  onRenameSource,
}) {
  const subscribedSources = sources.filter((source) => source.isSubscribed);
  const syncingAll =
    subscribedSources.length > 0 &&
    subscribedSources.every((source) => syncingSourceIds.includes(source.id));

  // 인라인 표시명 편집. editingRef 는 blur/Enter 중복 커밋을 막는 가드.
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState("");
  const editingRef = useRef(null);
  const editInputRef = useRef(null);

  // 편집 진입 시 입력에 포커스하고 기존 이름을 선택해 곧바로 덮어쓸 수 있게 한다.
  useEffect(() => {
    if (editingId != null && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  const startEdit = (source) => {
    editingRef.current = source.id;
    setEditingId(source.id);
    setDraft(source.displayName);
  };

  const cancelEdit = () => {
    editingRef.current = null;
    setEditingId(null);
  };

  const commitEdit = (source) => {
    if (editingRef.current !== source.id) return;
    editingRef.current = null;
    setEditingId(null);
    const name = draft.trim();
    if (name && name !== source.displayName) onRenameSource?.(source.id, name);
  };

  const MENU = [
    { id: "all", label: "전체", Icon: Globe, badge: null },
    { id: "ai", label: "AI 추천", Icon: Sparkles, badge: aiCount },
    { id: "saved", label: "저장됨", Icon: Bookmark, badge: savedCount },
  ];

  return (
    <aside className="sidebar">
      <nav className="menu" aria-label="공지 보기 필터">
        {MENU.map(({ id, label, Icon, badge }) => (
          <button
            key={id}
            className={`menuItem ${selectedView === id ? "active" : ""}`}
            aria-current={selectedView === id ? "page" : undefined}
            onClick={() => onChangeView(id)}
          >
            <span className="menuLeft">
              <Icon size={18} className="menuIcon" />
              {label}
            </span>
            {badge > 0 && <strong className="menuBadge">{badge}</strong>}
          </button>
        ))}
      </nav>

      <div className="divider" />

      <div className="siteListHead">
        <span className="sideTitle" style={{ margin: 0, padding: 0 }}>
          내 사이트
        </span>
        {subscribedSources.length > 0 && onSyncAll && (
          <button
            type="button"
            className="syncAllButton"
            onClick={onSyncAll}
            disabled={syncingAll}
            title="구독 중인 모든 사이트에서 새 공지 가져오기"
          >
            <RefreshCw size={13} className={syncingAll ? "spin" : ""} /> 전체 동기화
          </button>
        )}
      </div>

      <div className="siteList">
        {subscribedSources.length === 0 ? (
          <p className="siteListEmpty">등록된 사이트가 없어요.</p>
        ) : (
          subscribedSources.map((source) => {
            const isActive = activeSourceIds.includes(source.id);
            const isSyncing = syncingSourceIds.includes(source.id);
            const isEditing = editingId === source.id;

            return (
              <div className="siteRow" key={source.id}>
                {isEditing ? (
                  <input
                    ref={editInputRef}
                    className="siteRenameInput"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        commitEdit(source);
                      } else if (event.key === "Escape") {
                        event.preventDefault();
                        cancelEdit();
                      }
                    }}
                    onBlur={() => commitEdit(source)}
                    aria-label={`${source.displayName} 표시명 편집`}
                  />
                ) : (
                  <button
                    className={`sitePill ${isActive ? "active" : "inactive"}`}
                    aria-pressed={isActive}
                    title={`${source.displayName} · 더블클릭하면 이름을 바꿀 수 있어요`}
                    onClick={() => onToggleSource(source.id)}
                    onDoubleClick={() => startEdit(source)}
                  >
                    <SourceFavicon
                      name={source.displayName}
                      faviconUrl={source.faviconUrl}
                      size={22}
                      rounded="7px"
                    />
                    <span className="sitePillName">{source.displayName}</span>
                  </button>
                )}
                <button
                  type="button"
                  className="syncPillButton"
                  onClick={() => onSyncSource?.(source.id)}
                  disabled={isSyncing || isEditing}
                  title={isSyncing ? "가져오는 중..." : "새 공지 동기화"}
                  aria-label={`${source.displayName} 새 공지 동기화`}
                >
                  <RefreshCw size={15} className={isSyncing ? "spin" : ""} />
                </button>
              </div>
            );
          })
        )}
      </div>

      <button className="addSite" onClick={onOpenSiteRegister}>
        <Plus size={16} /> 사이트 등록
      </button>
    </aside>
  );
}

export default Sidebar;
