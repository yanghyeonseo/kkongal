import { useState } from "react";
import { Globe, Plus, Trash2, Loader2 } from "lucide-react";
import ModalShell from "./ModalShell.jsx";
import { useToast } from "../context/toast.js";
import {
  createSourceSubscription,
  deleteSourceSubscription,
} from "../api/sourceApi.js";

function isValidHttpUrl(value) {
  try {
    const parsed = new URL(value.trim());
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function SiteRegisterModal({ sources, onClose, onSourceAdded, onSourceRemoved }) {
  const toast = useToast();

  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!isValidHttpUrl(url)) {
      toast.error("http(s):// 로 시작하는 올바른 URL을 입력해주세요.");
      return;
    }

    setSubmitting(true);
    try {
      const source = await createSourceSubscription({ url: url.trim() });
      onSourceAdded?.(source);
      setUrl("");
      toast.success("사이트를 등록했어요.");
    } catch (error) {
      toast.error(error.message || "사이트 등록에 실패했어요.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (source) => {
    setDeletingId(source.subscriptionId);
    try {
      await deleteSourceSubscription(source.subscriptionId);
      onSourceRemoved?.(source);
      toast.success("사이트를 삭제했어요.");
    } catch (error) {
      toast.error(error.message || "사이트 삭제에 실패했어요.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <ModalShell
      className="registerModal"
      labelledBy="siteModalTitle"
      onClose={onClose}
    >
      <div className="registerModalHeader">
        <div>
          <h2 id="siteModalTitle">사이트 관리</h2>
          <p>공지를 수집할 사이트를 등록하고 관리하세요.</p>
        </div>
        <button
          type="button"
          className="modalCloseButton"
          onClick={onClose}
          aria-label="닫기"
        >
          ×
        </button>
      </div>

      <div className="registerModalBody">
        <form onSubmit={handleSubmit}>
          <label className="formLabel" htmlFor="siteUrlInput">
            공지 URL
          </label>
          <div className="modalInputBox">
            <Globe size={18} className="inputLeadingIcon" aria-hidden="true" />
            <input
              id="siteUrlInput"
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://example.com/notice"
            />
          </div>
          <p className="fieldHint">
            공지 목록이 있는 페이지 주소를 넣어주세요. 등록하면 주기적으로 새 공지를
            수집해요.
          </p>

          <button type="submit" className="aiStartButton" disabled={submitting}>
            {submitting ? (
              <>
                <Loader2 size={16} className="spin" /> 등록 중...
              </>
            ) : (
              <>
                <Plus size={16} /> 사이트 등록
              </>
            )}
          </button>
        </form>

        <div className="registerDivider" />

        <div className="registerListHead">
          <span>등록된 사이트</span>
          <strong>{sources.length}개</strong>
        </div>

        {sources.length === 0 ? (
          <div className="emptyTagBox">아직 등록한 사이트가 없어요.</div>
        ) : (
          <ul className="registeredSiteList">
            {sources.map((source) => (
              <li key={source.subscriptionId} className="registeredSiteItem">
                <div className="registeredSiteInfo">
                  <strong>{source.displayName}</strong>
                  <span>{source.url}</span>
                </div>
                <button
                  type="button"
                  className="iconGhostButton danger"
                  onClick={() => handleDelete(source)}
                  disabled={deletingId === source.subscriptionId}
                  aria-label={`${source.displayName} 삭제`}
                >
                  {deletingId === source.subscriptionId ? (
                    <Loader2 size={15} className="spin" />
                  ) : (
                    <Trash2 size={15} />
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </ModalShell>
  );
}

export default SiteRegisterModal;
