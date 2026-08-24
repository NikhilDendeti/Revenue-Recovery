const ACCESS_KEY = "recoverai_access_token";
const REFRESH_KEY = "recoverai_refresh_token";

export function getAccessToken() {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY);
}

export function isAuthenticated() {
  return Boolean(getAccessToken());
}

function setTokens({ access, refresh }) {
  if (access) localStorage.setItem(ACCESS_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
}

export function logout() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export async function login(username, password) {
  const res = await fetch("/api/auth/token/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    throw new Error("Invalid username or password");
  }
  const data = await res.json();
  setTokens(data);
  return data;
}

// One silent refresh attempt — used by api.js on a 401. Returns the new access
// token, or null if the refresh token itself is missing/expired (caller should then
// force a full re-login rather than retrying again).
export async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  const res = await fetch("/api/auth/token/refresh/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) {
    logout();
    return null;
  }
  const data = await res.json();
  setTokens({ access: data.access });
  return data.access;
}
