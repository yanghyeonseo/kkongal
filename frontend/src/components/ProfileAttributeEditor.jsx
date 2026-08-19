import { useState } from "react";
import { Pencil, Trash2, Plus, Check, X, Loader2 } from "lucide-react";

// 도메인을 가리지 않고 대부분의 사람이 공감할 만한 보편적 배경/자격 예시.
// 진로·취업에 치우치지 않도록 생활 전반(주거·가족·소비·취미·지역)에서 고른다.
// 온보딩·설정 두 편집기가 같은 목록을 쓰도록 여기 한 곳에서만 정의한다.
export const PROFILE_FIELD_SUGGESTIONS = [
  "거주 형태",
  "결혼 여부",
  "자녀 유무",
  "반려동물",
  "차량 보유",
  "사용 통신사",
  "관심 취미",
  "자주 가는 지역",
  "MBTI",
  "관심 브랜드",
];

/**
 * 사용자 지정 프로필 필드(label — value) 목록 편집기.
 * 자체 API 호출 없이 부모가 넘긴 콜백만 호출한다(온보딩·설정 양쪽에서 재사용).
 * 부모가 목록 상태를 소유하고, 실패 시 toast 노출도 부모 몫이다. 여기서는 콜백을
 * await 해서 성공했을 때만 입력을 비우고, 실패(throw)하면 입력을 유지한다.
 *
 * props:
 *   attributes   — [{ id, label, value }] 현재 목록
 *   onCreate     — async (label, value) => void  생성
 *   onUpdate     — async (id, label, value) => void  수정
 *   onDelete     — async (id) => void  삭제
 *   suggestions  — 클릭 시 label 입력을 채우는 예시 칩(기본: 보편 필드 예시)
 */
function ProfileAttributeEditor({
  attributes,
  onCreate,
  onUpdate,
  onDelete,
  suggestions = PROFILE_FIELD_SUGGESTIONS,
}) {
  const [label, setLabel] = useState("");
  const [value, setValue] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  const resetForm = () => {
    setLabel("");
    setValue("");
    setEditingId(null);
  };

  const handleSubmit = async () => {
    const trimmedLabel = label.trim();
    const trimmedValue = value.trim();
    // 항목/내용 둘 다 있어야 의미가 있다.
    if (!trimmedLabel || !trimmedValue) return;

    setSubmitting(true);
    try {
      if (editingId) {
        await onUpdate(editingId, trimmedLabel, trimmedValue);
      } else {
        await onCreate(trimmedLabel, trimmedValue);
      }
      resetForm();
    } catch {
      // 실패하면 입력을 유지한다(부모가 toast 로 알린다).
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = (item) => {
    setEditingId(item.id);
    setLabel(item.label);
    setValue(item.value);
  };

  const handleDelete = async (item) => {
    setDeletingId(item.id);
    try {
      await onDelete(item.id);
      if (editingId === item.id) resetForm();
    } catch {
      // 부모가 toast 로 알린다.
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
    <div className="attrEditor">
      {attributes.length === 0 ? (
        <div className="emptyTagBox">아직 추가한 정보가 없어요.</div>
      ) : (
        <ul className="interestList attrList">
          {attributes.map((item) => (
            <li
              key={item.id}
              className={`interestItem attrItem ${editingId === item.id ? "editing" : ""}`}
            >
              <div className="interestItemMain attrItemMain">
                <span className="attrItemLabel">{item.label}</span>
                <span className="attrItemSep">—</span>
                <span className="attrItemValue">{item.value}</span>
              </div>

              <div className="interestItemActions">
                <button
                  type="button"
                  className="iconGhostButton"
                  onClick={() => handleEdit(item)}
                  aria-label={`${item.label} 수정`}
                >
                  <Pencil size={15} />
                </button>
                <button
                  type="button"
                  className="iconGhostButton danger"
                  onClick={() => handleDelete(item)}
                  disabled={deletingId === item.id}
                  aria-label={`${item.label} 삭제`}
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

      <div className="attrAddForm">
        <div className="attrInputRow">
          <input
            className="attrLabelInput"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="항목 (예: 학교)"
            aria-label="추가할 항목 이름"
          />
          <input
            className="attrValueInput"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="내용 (예: 서울대학교)"
            aria-label="추가할 항목 내용"
          />
          <button
            type="button"
            className="attrAddBtn"
            onClick={handleSubmit}
            disabled={submitting}
            aria-label={editingId ? "수정 완료" : "추가"}
          >
            {submitting ? (
              <Loader2 size={15} className="spin" />
            ) : editingId ? (
              <Check size={15} />
            ) : (
              <Plus size={15} />
            )}
          </button>
        </div>

        {editingId && (
          <button
            type="button"
            className="attrCancelBtn"
            onClick={resetForm}
            disabled={submitting}
          >
            <X size={14} /> 수정 취소
          </button>
        )}

        {suggestions.length > 0 && (
          <div className="attrSuggestions">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                className="attrSuggestChip"
                onClick={() => setLabel(suggestion)}
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default ProfileAttributeEditor;
