import { apiRequest } from "./client.js";

const USER_STORAGE_KEY = "kkongal_user";

// 백엔드 UserSerializer 응답을 프론트에서 쓰는 형태로 정규화한다.
// 백엔드는 username 으로 인증하고 email 은 알림용으로 따로 저장한다.
// 표시용 이름(name)은 username 을 사용한다(별도 name 필드가 없음).
function normalizeUser(data, fallback = {}) {
  const user = data ?? {};

  const name =
    user.username ??
    fallback.username ??
    fallback.name ??
    user.email?.split("@")[0] ??
    "사용자";

  return {
    id: user.id ?? fallback.id ?? null,
    username: user.username ?? fallback.username ?? name,
    name,
    email: user.email ?? fallback.email ?? "",
    age: user.age ?? null,
    job: user.job ?? "",
    gender: user.gender ?? "",
    // 온보딩 상태. 백엔드가 아직 필드를 안 내려주면(undefined) 위저드를 띄우지 않는다
    // (병렬 개발 안전장치). 명시적으로 false 일 때만 온보딩을 표시한다.
    onboarded: user.onboarded ?? fallback.onboarded ?? null,
  };
}

export function getStoredUser() {
  const savedUser = localStorage.getItem(USER_STORAGE_KEY);
  if (!savedUser) return null;

  try {
    return JSON.parse(savedUser);
  } catch {
    return null;
  }
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

// 회원가입: username + password 는 필수, email 은 알림에 필요, 나머지는 선택.
export async function signup({
  username,
  email,
  password,
  age = null,
  job = "",
  gender = "",
}) {
  const body = { username, email, password };

  // 선택 프로필(AI 추천 정확도 향상용)은 값이 있을 때만 전송
  if (age !== null && age !== "" && !Number.isNaN(Number(age))) {
    body.age = Number(age);
  }
  if (job) body.job = job;
  if (gender) body.gender = gender;

  const data = await apiRequest("/api/account/signup/", {
    method: "POST",
    body: JSON.stringify(body),
  });

  return normalizeUser(data, { username, email });
}

// 로그인: 백엔드는 username 으로 인증한다.
export async function login({ username, password }) {
  const data = await apiRequest("/api/account/signin/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });

  return normalizeUser(data, { username });
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
