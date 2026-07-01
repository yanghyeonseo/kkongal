import { apiRequest } from "./client.js";

const USER_STORAGE_KEY = "kkongal_user";
const USE_MOCK = true;

function normalizeUser(data, fallback = {}) {
  const user = data?.user ?? data?.data?.user ?? data ?? {};

  const name =
    user.name ??
    user.username ??
    fallback.name ??
    fallback.username ??
    fallback.email?.split("@")[0] ??
    "사용자";

  return {
    id: user.id ?? fallback.id ?? null,
    email: user.email ?? fallback.email ?? "",
    name,
    username: user.username ?? name,
    age: user.age ?? 0,
    job: user.job ?? "",
    gender: user.gender ?? "",
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

export async function getCurrentUser() {
  if (USE_MOCK) {
    return {
      id: 1,
      name: "김현서",
      username: "김현서",
      email: "test@example.com",
    };
  }

  const data = await apiRequest("/api/account/me/");
  return normalizeUser(data);
}

export async function signup({ name, email, password }) {
  if (USE_MOCK) {
    return {
      id: Date.now(),
      name,
      username: name,
      email,
    };
  }

  const data = await apiRequest("/api/account/signup/", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      username: name,
      age: 0,
      job: "",
      gender: "",
    }),
  });

  return normalizeUser(data, { name, email });
}

export async function login({ email, password }) {
  if (USE_MOCK) {
    return {
      id: 1,
      name: email.split("@")[0] || "김현서",
      username: email.split("@")[0] || "김현서",
      email,
    };
  }

  const data = await apiRequest("/api/account/signin/", {
    method: "POST",
    body: JSON.stringify({
      username: email,
      password,
    }),
  });

  return normalizeUser(data, { email });
}

export async function logout() {
  if (USE_MOCK) {
    return;
  }

  await apiRequest("/api/account/logout/", {
    method: "POST",
    body: JSON.stringify({
      refresh: "",
    }),
  });
}
