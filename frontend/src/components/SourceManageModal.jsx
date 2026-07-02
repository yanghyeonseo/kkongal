import { useState } from "react";
import { updateSourceSubscriptions } from "../api/sourceApi.js";

const CATEGORY_LABELS = {
  school: "학교 공지",
  job: "채용",
  scholarship: "장학금",
  activity: "대외활동",
  contest: "공모전",
  culture: "문화",
  community: "커뮤니티",
};

function SourceManageModal({ sources, onClose, onSave }) {
  const [selectedIds, setSelectedIds] = useState(
    sources.filter((source) => source.isSubscribed).map((source) => source.id),
  );

  const handleToggle = (sourceId) => {
    setSelectedIds((prev) => {
      if (prev.includes(sourceId)) {
        return prev.filter((id) => id !== sourceId);
      }

      return [...prev, sourceId];
    });
  };

  const handleSave = async () => {
    await updateSourceSubscriptions(selectedIds);
    onSave(selectedIds);
    onClose();
  };

  const groupedSources = sources.reduce((acc, source) => {
    if (!acc[source.category]) {
      acc[source.category] = [];
    }

    acc[source.category].push(source);
    return acc;
  }, {});

  return (
    <div className="modalOverlay">
      <div className="sourceModal">
        <div className="modalHeader">
          <div>
            <p>관심 사이트 관리</p>
            <h2>받아볼 공지 출처를 선택하세요</h2>
          </div>

          <button className="modalCloseButton" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="sourceGroupList">
          {Object.entries(groupedSources).map(([category, items]) => (
            <section key={category} className="sourceGroup">
              <h3>{CATEGORY_LABELS[category]}</h3>

              <div className="sourceCheckList">
                {items.map((source) => (
                  <label key={source.id} className="sourceCheckItem">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(source.id)}
                      onChange={() => handleToggle(source.id)}
                    />

                    <div>
                      <strong>{source.displayName}</strong>
                      <span>{source.url}</span>
                    </div>
                  </label>
                ))}
              </div>
            </section>
          ))}
        </div>

        <div className="modalFooter">
          <button className="cancelButton" onClick={onClose}>
            취소
          </button>

          <button className="saveButton" onClick={handleSave}>
            선택 저장
          </button>
        </div>
      </div>
    </div>
  );
}

export default SourceManageModal;
