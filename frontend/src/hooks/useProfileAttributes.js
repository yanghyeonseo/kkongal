import { useEffect, useState } from "react";
import { useToast } from "../context/toast.js";
import {
  getProfileAttributes,
  createProfileAttribute,
  updateProfileAttribute,
  deleteProfileAttribute,
} from "../api/profileApi.js";

/**
 * 사용자 지정 프로필 필드(ProfileAttribute) 목록 상태 + 즉시 저장 CRUD.
 *
 * 온보딩 위저드와 '내 정보 설정' 모달이 동일한 로딩·갱신·에러 처리를 공유하도록
 * 한 곳에 모은다. 각 변경은 서버에 바로 반영하고, 실패하면 toast 로 알린 뒤 에러를
 * 다시 던져 ProfileAttributeEditor 가 입력을 유지하도록 한다. 삭제는 낙관적으로
 * 먼저 지우고 실패 시 스냅샷으로 되돌린다.
 *
 * 반환한 create/update/remove 는 ProfileAttributeEditor 의 onCreate/onUpdate/onDelete
 * 콜백 시그니처(label,value / id,label,value / id)에 그대로 맞춰져 있다.
 */
export function useProfileAttributes() {
  const toast = useToast();
  const [attributes, setAttributes] = useState([]); // { id, label, value }

  useEffect(() => {
    let active = true;
    getProfileAttributes()
      .then((list) => {
        if (active) setAttributes(list);
      })
      .catch(() => {
        // 로드 실패해도 화면을 막지 않는다(빈 목록으로 시작).
        if (active) toast.error("추가 정보를 불러오지 못했어요.");
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const create = async (label, value) => {
    try {
      const created = await createProfileAttribute({ label, value });
      setAttributes((prev) => [created, ...prev]);
    } catch (error) {
      toast.error(error.message || "추가 정보 저장에 실패했어요.");
      throw error;
    }
  };

  const update = async (id, label, value) => {
    try {
      const updated = await updateProfileAttribute(id, { label, value });
      setAttributes((prev) => prev.map((item) => (item.id === id ? updated : item)));
    } catch (error) {
      toast.error(error.message || "추가 정보 수정에 실패했어요.");
      throw error;
    }
  };

  const remove = async (id) => {
    const snapshot = attributes;
    setAttributes((prev) => prev.filter((item) => item.id !== id));
    try {
      await deleteProfileAttribute(id);
    } catch (error) {
      setAttributes(snapshot); // 실패 시 되돌리기
      toast.error(error.message || "추가 정보 삭제에 실패했어요.");
      throw error;
    }
  };

  return { attributes, create, update, remove };
}
