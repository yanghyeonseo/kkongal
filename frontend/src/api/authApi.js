import { apiRequest } from "./client.js";

const USER_STORAGE_KEY = "kkongal_user";

// 백엔드 UserSerializer 응답을 프론트에서 쓰는 형태로 정규화한다.
// 로그인 ID 는 이메일이다. 백엔드의 username 은 이메일에서 자동 생성한 내부 식별자라
// 응답에 실리지 않으며, 표시용 이름(name)은 nickname → 이메일 로컬파트 순으로 정한다.
export function normalizeUser(data, fallback = {}) {
  const user = data ?? {};

  const email = user.email ?? fallback.email ?? "";
  const nickname = user.nickname ?? fallback.nickname ?? "";
  const name = nickname || email.split("@")[0] || "사용자";

  return {
    id: user.id ?? fallback.id ?? null,
    name,
    nickname,
    email,
    // 이메일 인증 여부. 백엔드가 아직 필드를 안 내려주면(undefined) 인증 배너를
    // 띄우지 않는다 — 명시적으로 false 일 때만 미인증으로 취급한다.
    emailVerified: user.email_verified ?? fallback.emailVerified ?? null,
    age: user.age ?? null,
    job: user.job ?? "",
    gender: user.gender ?? "",
    // 고정 프로필 필드(나이/성별/지역/직업) + 자유서술(bio) catch-all.
    // 도메인별 특화 정보는 ProfileAttribute(사용자 지정 커스텀 필드)로 분리됐다.
    region: user.region ?? "",
    bio: user.bio ?? "",
    // 온보딩 상태. 백엔드가 아직 필드를 안 내려주면(undefined) 위저드를 띄우지 않는다
    // (병렬 개발 안전장치). 명시적으로 false 일 때만 온보딩을 표시한다.
    onboarded: user.onboarded ?? fallback.onboarded ?? null,
  };
}

export function saveStoredUser(user) {
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
}

export function clearStoredUser() {
  localStorage.removeItem(USER_STORAGE_KEY);
}

// 쿠키의 access_token 기준으로 현재 로그인 사용자를 조회한다.
export async function getCurrentUser() {
  const data = await apiRequest("/api/account/me/");
  return normalizeUser(data);
}

// 회원가입: 이메일 + 비밀번호만 받는다. 닉네임은 온보딩 첫 단계에서 따로 묻는다.
export async function signup({
  email,
  password,
  age = null,
  job = "",
  gender = "",
  region = "",
}) {
  const body = { email, password };

  // 선택 프로필(AI 추천 정확도 향상용)은 값이 있을 때만 전송
  if (age !== null && age !== "" && !Number.isNaN(Number(age))) {
    body.age = Number(age);
  }
  if (job) body.job = job;
  if (gender) body.gender = gender;
  if (region) body.region = region;

  const data = await apiRequest("/api/account/signup/", {
    method: "POST",
    body: JSON.stringify(body),
  });

  return normalizeUser(data, { email });
}

// 로그인: 백엔드는 이메일로 인증한다.
export async function login({ email, password }) {
  const data = await apiRequest("/api/account/signin/", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

  return normalizeUser(data, { email });
}

// 메일 링크의 토큰으로 이메일 인증을 완료한다(로그인 없이도 호출 가능).
export async function verifyEmail(token) {
  return apiRequest("/api/account/verify-email/", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

// 인증 메일 재발송(로그인 상태에서 본인에게만).
export async function resendVerificationEmail() {
  return apiRequest("/api/account/verify-email/resend/", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

// 온보딩 완료: request.user.onboarded = True 후 user 반환.
export async function completeOnboarding() {
  const data = await apiRequest("/api/account/onboarding/complete/", {
    method: "POST",
    body: JSON.stringify({}),
  });
  return normalizeUser(data);
}

export async function logout() {
  // refresh_token 은 쿠키로 전달된다(백엔드가 쿠키 우선으로 읽음).
  await apiRequest("/api/account/logout/", {
    method: "POST",
    body: JSON.stringify({}),
  });
}
