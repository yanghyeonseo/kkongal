function SiteRegisterModal({ onClose }) {
  return (
    <div className="modalOverlay">
      <div className="registerModal">
        <div className="registerModalHeader">
          <div>
            <h2>사이트 등록</h2>
            <p>공지를 수집할 사이트 정보를 입력하세요</p>
          </div>

          <button className="modalCloseButton" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="registerModalBody">
          <label className="formLabel">사이트 이름</label>
          <div className="modalInputBox">
            <span>📌</span>
            <input placeholder="예: 서울대 컴공 공지" />
          </div>

          <label className="formLabel">공지 URL</label>
          <div className="modalInputBox">
            <span>🌐</span>
            <input placeholder="https://example.com/notice" />
          </div>

          <button className="aiStartButton" onClick={onClose}>
            사이트 등록
          </button>
        </div>
      </div>
    </div>
  );
}

export default SiteRegisterModal;
