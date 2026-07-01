import { apiRequest } from "./client.js";

const USER_STORAGE_KEY = "kkongal_user";

function normalizeUser(data, fallback = {}) {
  const user = data?.user ?? data?.data?.user ?? data ?? {};

  const name =
    user.name ??
    user.username ??
    fallback.name ??
    fallback.email?.split("@")[0] ??
    "사용자";

  return {
    id: user.id ?? fallback.id ?? null,
    email: user.email ?? fallback.email ?? "",
    name,
  };
}

export function getStoredUser() {
  const savedUser = localStorage.getItem(USER_STORAGE_KEY);

  if (!savedUser) {
    return null;
  }

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

export async function signup({ name, email, password }) {
  const data = await apiRequest("/api/account/signup/", {
    method: "POST",
    body: JSON.stringify({
      name,
      email,
      password,
    }),
  });

  return normalizeUser(data, { name, email });
}

export async function login({ email, password }) {
  const data = await apiRequest("/api/account/login/", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
    }),
  });

  return normalizeUser(data, { email });
}

export async function logout() {
  await apiRequest("/api/account/logout/", {
    method: "POST",
  });
}
