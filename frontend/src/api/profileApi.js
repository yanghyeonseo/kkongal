import { apiRequest } from "./client.js";
import { normalizeUser } from "./authApi.js";

// 프로필(고정 필드 + 자유서술) 부분 갱신에 쓰이는 키 목록.
// username/password/email/onboarded/created_at 은 이 엔드포인트로 못 바꾼다.
const PROFILE_FIELDS = ["age", "job", "gender", "region", "bio"];

// 프로필 부분 갱신: fields 에 존재하는 키만 payload 에 담는다(빈 문자열도 포함되어
// 설정 모달에서 값을 명시적으로 비울 수 있다). age 는 숫자로 변환되며, 숫자가 아니면 null.
export async function updateProfile(fields) {
  const payload = {};

  for (const key of PROFILE_FIELDS) {
    if (!(key in fields)) continue;

    if (key === "age") {
      const age = fields.age;
      payload.age =
        age !== null && age !== "" && !Number.isNaN(Number(age))
          ? Number(age)
          : null;
      continue;
    }

    payload[key] = fields[key];
  }

  const data = await apiRequest("/api/account/profile/", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

  return normalizeUser(data);
}

// 사용자 지정 커스텀 필드(ProfileAttribute) CRUD. 도메인별로 달라지는 배경/자격 정보를
// 사용자가 직접 label/value 쌍으로 추가한다(interestApi.js 와 동일한 패턴).
function normalizeProfileAttribute(item) {
  return {
    id: item.id,
    label: item.label ?? "",
    value: item.value ?? "",
  };
}

export async function getProfileAttributes() {
  const data = await apiRequest("/api/account/profile/attributes/");
  return Array.isArray(data) ? data.map(normalizeProfileAttribute) : [];
}

export async function createProfileAttribute({ label, value }) {
  const data = await apiRequest("/api/account/profile/attributes/", {
    method: "POST",
    body: JSON.stringify({ label, value }),
  });
  return normalizeProfileAttribute(data);
}

export async function updateProfileAttribute(attributeId, { label, value }) {
  const data = await apiRequest(
    `/api/account/profile/attributes/${attributeId}/`,
    {
      method: "PUT",
      body: JSON.stringify({ label, value }),
    },
  );
  return normalizeProfileAttribute(data);
}

export async function deleteProfileAttribute(attributeId) {
  return apiRequest(`/api/account/profile/attributes/${attributeId}/`, {
    method: "DELETE",
  });
}
