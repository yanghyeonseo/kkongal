import { useState } from "react";
import { updateMyInterests } from "../api/interestApi.js";

function InterestSettingModal({ interests, onClose, onSave }) {
  const [localInterests, setLocalInterests] = useState(interests);
  const [inputValue, setInputValue] = useState("");

  const handleAddInterest = () => {
    const keyword = inputValue.trim();

    if (!keyword) {
      return;
    }

    const alreadyExists = localInterests.some(
      (interest) => interest.keyword === keyword,
    );

    if (alreadyExists) {
      setInputValue("");
      return;
    }

    const newInterest = {
      id: Date.now(),
      keyword,
    };

    setLocalInterests((prev) => [...prev, newInterest]);
    setInputValue("");
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleAddInterest();
    }
  };

  const handleRemoveInterest = (interestId) => {
    setLocalInterests((prev) =>
      prev.filter((interest) => interest.id !== interestId),
    );
  };

  const handleSave = async () => {
    const savedInterests = await updateMyInterests(localInterests);
    onSave(savedInterests);
    onClose();
  };

  return (
    <div className="modalOverlay">
      <div className="interestModal">
        <div className="registerModalHeader">
          <div>
            <h2>관심사 설정</h2>
            <p>AI가 공지를 선별할 때 사용할 관심 태그를 관리하세요</p>
          </div>

          <button className="modalCloseButton" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="interestModalBody">
          <section className="currentTagSection">
            <div className="sectionTitleRow">
              <div>
                <h3>현재 관심 태그</h3>
                <p>등록된 태그를 기준으로 AI가 공지를 추천합니다.</p>
              </div>

              <strong>{localInterests.length}개</strong>
            </div>

            {localInterests.length === 0 ? (
              <div className="emptyTagBox">아직 등록된 관심 태그가 없어요.</div>
            ) : (
              <div className="currentTagList">
                {localInterests.map((interest) => (
                  <button
                    key={interest.id}
                    className="interestTag"
                    onClick={() => handleRemoveInterest(interest.id)}
                  >
                    {interest.keyword} ×
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="addTagSection">
            <label className="formLabel">새 관심 태그 추가</label>

            <div className="addTagInputRow">
              <input
                value={inputValue}
                onChange={(event) => setInputValue(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="예: 백엔드, 인턴, 서울"
              />

              <button onClick={handleAddInterest}>추가</button>
            </div>

            <p className="tagHelpText">
              Enter를 누르거나 추가 버튼을 누르면 태그가 추가됩니다.
            </p>
          </section>

          <div className="interestPreviewBox">
            <p>현재 AI 추천 기준</p>
            <strong>
              {localInterests.length > 0
                ? localInterests.map((interest) => interest.keyword).join(" / ")
                : "아직 등록된 관심사가 없습니다"}
            </strong>
          </div>

          <button className="aiStartButton" onClick={handleSave}>
            관심사 저장
          </button>
        </div>
      </div>
    </div>
  );
}

export default InterestSettingModal;
