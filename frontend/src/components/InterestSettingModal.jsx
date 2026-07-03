import { useState } from "react";
import { Pencil, Trash2, Plus, Check, X, Loader2 } from "lucide-react";
import ModalShell from "./ModalShell.jsx";
import { useToast } from "../context/toast.js";
import {
  createInterest,
  updateInterest,
  deleteInterest,
} from "../api/interestApi.js";

const PRIORITY_OPTIONS = [
  { value: 2, label: "높음" },
  { value: 1, label: "보통" },
  { value: 0, label: "낮음" },
];

function priorityLabel(value) {
  return PRIORITY_OPTIONS.find((option) => option.value === value)?.label || "보통";
}

function InterestSettingModal({ interests, onClose, onInterestsChange }) {
  const toast = useToast();

  const [items, setItems] = useState(interests);
  const [keyword, setKeyword] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState(1);
  const [editingId, setEditingId] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  const sync = (nextItems) => {
    setItems(nextItems);
    onInterestsChange?.(nextItems);
  };

  const resetForm = () => {
    setKeyword("");
    setDescription("");
    setPriority(1);
    setEditingId(null);
  };

  const handleSubmit = async () => {
    const trimmed = keyword.trim();
    if (!trimmed) {
      toast.error("관심 키워드를 입력해주세요.");
      return;
    }

    const duplicate = items.some(
      (item) => item.keyword === trimmed && item.id !== editingId,
    );
    if (duplicate) {
      toast.info("이미 등록된 키워드예요.");
      return;
    }

    setSubmitting(true);
    try {
      if (editingId) {
        const updated = await updateInterest(editingId, {
          keyword: trimmed,
          description: description.trim(),
          priority,
        });
        sync(items.map((item) => (item.id === editingId ? updated : item)));
        toast.success("관심사를 수정했어요.");
      } else {
        const created = await createInterest({
          keyword: trimmed,
          description: description.trim(),
          priority,
        });
        sync([...items, created]);
        toast.success("관심사를 추가했어요.");
      }
      resetForm();
    } catch (error) {
      toast.error(error.message || "관심사 저장에 실패했어요.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = (item) => {
    setEditingId(item.id);
    setKeyword(item.keyword);
    setDescription(item.description || "");
    setPriority(item.priority ?? 1);
  };

  const handleDelete = async (item) => {
    setDeletingId(item.id);
    try {
      await deleteInterest(item.id);
      sync(items.filter((current) => current.id !== item.id));
      if (editingId === item.id) resetForm();
      toast.success("관심사를 삭제했어요.");
    } catch (error) {
      toast.error(error.message || "관심사 삭제에 실패했어요.");
    } finally {
      setDeletingId(null);
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleSubmit();
    }
  };

  return (
    <ModalShell
      size="lg"
      onClose={onClose}
      title="관심사 설정"
      subtitle="AI가 공지를 선별할 때 사용할 관심 조건을 관리하세요."
    >
      <section className="currentTagSection">
          <div className="sectionTitleRow">
            <div>
              <h3>현재 관심 조건</h3>
              <p>등록된 조건을 기준으로 AI가 공지를 추천합니다.</p>
            </div>
            <strong>{items.length}개</strong>
          </div>

          {items.length === 0 ? (
            <div className="emptyTagBox">아직 등록된 관심 조건이 없어요.</div>
          ) : (
            <ul className="interestList">
              {items.map((item) => (
                <li
                  key={item.id}
                  className={`interestItem ${editingId === item.id ? "editing" : ""}`}
                >
                  <div className="interestItemMain">
                    <div className="interestItemHead">
                      <strong>{item.keyword}</strong>
                      <span className={`priorityBadge p${item.priority}`}>
                        {priorityLabel(item.priority)}
                      </span>
                    </div>
                    {item.description && (
                      <p className="interestItemDesc">{item.description}</p>
                    )}
                  </div>

                  <div className="interestItemActions">
                    <button
                      type="button"
                      className="iconGhostButton"
                      onClick={() => handleEdit(item)}
                      aria-label={`${item.keyword} 수정`}
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      type="button"
                      className="iconGhostButton danger"
                      onClick={() => handleDelete(item)}
                      disabled={deletingId === item.id}
                      aria-label={`${item.keyword} 삭제`}
                    >
                      {deletingId === item.id ? (
                        <Loader2 size={15} className="spin" />
                      ) : (
                        <Trash2 size={15} />
                      )}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="addTagSection">
          <label className="formLabel" htmlFor="interestKeyword">
            {editingId ? "관심 조건 수정" : "새 관심 조건 추가"}
          </label>

          <div className="addTagInputRow">
            <input
              id="interestKeyword"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="키워드 (예: 백엔드, 인턴, 서울)"
            />
          </div>

          <textarea
            className="interestDescInput"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="자연어 설명 (선택) — 예: 신입도 지원 가능한 서울 지역 백엔드 인턴"
            rows={2}
          />

          <div className="priorityRow">
            <span className="priorityRowLabel">우선순위</span>
            <div className="priorityChips" role="group" aria-label="우선순위 선택">
              {PRIORITY_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`priorityChip ${priority === option.value ? "active" : ""}`}
                  aria-pressed={priority === option.value}
                  onClick={() => setPriority(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="addTagButtonRow">
            {editingId && (
              <button
                type="button"
                className="ghostButton"
                onClick={resetForm}
                disabled={submitting}
              >
                <X size={15} /> 취소
              </button>
            )}
            <button
              type="button"
              className="primaryButton"
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting ? (
                <Loader2 size={15} className="spin" />
              ) : editingId ? (
                <Check size={15} />
              ) : (
                <Plus size={15} />
              )}
              {editingId ? "수정 완료" : "추가"}
            </button>
          </div>
        </section>

        <div className="interestPreviewBox">
          <p>현재 AI 추천 기준</p>
          <strong>
            {items.length > 0
              ? items.map((item) => item.keyword).join(" / ")
              : "아직 등록된 관심사가 없습니다"}
          </strong>
        </div>
    </ModalShell>
  );
}

export default InterestSettingModal;
