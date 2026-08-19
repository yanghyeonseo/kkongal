import { useState } from "react";
import { Check, Loader2 } from "lucide-react";
import ModalShell from "./ModalShell.jsx";
import ProfileAttributeEditor from "./ProfileAttributeEditor.jsx";
import { useToast } from "../context/toast.js";
import { updateProfile } from "../api/profileApi.js";
import { useProfileAttributes } from "../hooks/useProfileAttributes.js";

// 성별만 선택지가 정해져 있어 select 로 받고, 나머지 고정 필드는 스케일·표기가
// 제각각이라 자유 입력(text)으로 받는다. bio 는 고정 필드로 못 담는 맥락을 담는 catch-all.
const GENDER_OPTIONS = ["남성", "여성", "기타"];

// select 에 저장된 값이 프리셋에 없더라도 유실되지 않게 현재 값을 옵션으로 포함시킨다.
function optionsWith(current, presets) {
  if (current && !presets.includes(current)) return [current, ...presets];
  return presets;
}

function ProfileSettingModal({ currentUser, onClose, onSaved }) {
  const toast = useToast();

  const [form, setForm] = useState(() => ({
    age: currentUser?.age != null ? String(currentUser.age) : "",
    gender: currentUser?.gender || "",
    job: currentUser?.job || "",
    region: currentUser?.region || "",
    bio: currentUser?.bio || "",
  }));
  const [submitting, setSubmitting] = useState(false);

  // Section B(사용자 지정 필드) — 로딩·즉시 저장·에러 처리는 온보딩과 공유하는 훅에 위임.
  const {
    attributes,
    create: handleCreateAttribute,
    update: handleUpdateAttribute,
    remove: handleDeleteAttribute,
  } = useProfileAttributes();

  const setField = (key) => (event) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const handleSubmit = async () => {
    // age 는 정수(IntegerField)라 숫자만 보낸다. 비우면 null 로 초기화.
    const trimmedAge = form.age.trim();
    const parsedAge = trimmedAge === "" ? null : Number(trimmedAge);
    if (parsedAge != null && (!Number.isInteger(parsedAge) || parsedAge < 0)) {
      toast.error("나이는 0 이상의 정수로 입력해주세요.");
      return;
    }

    setSubmitting(true);
    try {
      const updated = await updateProfile({
        age: parsedAge,
        gender: form.gender,
        job: form.job.trim(),
        region: form.region.trim(),
        bio: form.bio.trim(),
      });
      onSaved?.(updated);
      toast.success("내 정보를 저장했어요.");
      onClose();
    } catch (error) {
      toast.error(error.message || "내 정보 저장에 실패했어요.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell
      size="lg"
      onClose={onClose}
      title="내 정보 설정"
      subtitle="관심사와 함께 이 정보를 참고해 AI가 더 정확히 공지를 선별해요."
    >
      <section className="profileSection">
        <div className="profileGrid">
          <div className="profileField">
            <label className="formLabel" htmlFor="profileAge">
              나이
            </label>
            <input
              id="profileAge"
              type="number"
              min="0"
              inputMode="numeric"
              value={form.age}
              onChange={setField("age")}
              placeholder="예: 24"
            />
          </div>

          <div className="profileField">
            <label className="formLabel" htmlFor="profileGender">
              성별
            </label>
            <select id="profileGender" value={form.gender} onChange={setField("gender")}>
              <option value="">선택 안 함</option>
              {optionsWith(form.gender, GENDER_OPTIONS).map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>

          <div className="profileField">
            <label className="formLabel" htmlFor="profileJob">
              직업·직군
            </label>
            <input
              id="profileJob"
              value={form.job}
              onChange={setField("job")}
              placeholder="예: 대학생, 백엔드 개발자"
            />
          </div>

          <div className="profileField">
            <label className="formLabel" htmlFor="profileRegion">
              거주·활동 지역
            </label>
            <input
              id="profileRegion"
              value={form.region}
              onChange={setField("region")}
              placeholder="예: 서울 관악구"
            />
          </div>
        </div>

        <div className="profileBioField">
          <label className="formLabel" htmlFor="profileBio">
            기타 · 당신에 대해 자유롭게 알려주세요
          </label>
          <textarea
            id="profileBio"
            className="interestDescInput profileBioInput"
            value={form.bio}
            onChange={setField("bio")}
            placeholder="정형 항목에 없는 건 뭐든 자유롭게 (예: 다자녀 가정, 반려견과 거주, 주말 등산 애호가)"
            rows={4}
          />
        </div>

        <div className="addTagButtonRow">
          <button
            type="button"
            className="primaryButton"
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? <Loader2 size={15} className="spin" /> : <Check size={15} />}
            저장
          </button>
        </div>
      </section>

      <section className="profileSection profileAttrSection">
        <div className="sectionTitleRow">
          <div>
            <h3>추가 정보 · 내가 만든 필드</h3>
            <p>도메인에 맞는 배경·자격을 직접 추가하세요. 추가/수정/삭제는 바로 저장돼요.</p>
          </div>
          <strong>{attributes.length}개</strong>
        </div>

        <ProfileAttributeEditor
          attributes={attributes}
          onCreate={handleCreateAttribute}
          onUpdate={handleUpdateAttribute}
          onDelete={handleDeleteAttribute}
        />
      </section>
    </ModalShell>
  );
}

export default ProfileSettingModal;
