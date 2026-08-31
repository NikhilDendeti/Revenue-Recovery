import { getAccessToken, logout, refreshAccessToken } from "./auth";
import { API_ROOT } from "./config";

const BASE = API_ROOT;

let onSessionExpired = null;
export function setSessionExpiredHandler(fn) {
  onSessionExpired = fn;
}

async function req(path, options = {}, isRetry = false) {
  const token = getAccessToken();
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...options,
  });

  if (res.status === 401 && !isRetry) {
    const newToken = await refreshAccessToken();
    if (newToken) return req(path, options, true);
    logout();
    onSessionExpired?.();
    throw new Error("Session expired — please log in again");
  }

  if (!res.ok) {
    throw new Error(`${options.method || "GET"} ${path} -> ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  summary: () => req("/summary/"),
  transactions: (params = "") => req(`/transactions/${params}`),
  transactionChain: (id) => req(`/transactions/${id}/chain/`),
  auditLog: (params = "") => req(`/audit-log/${params}`),
  promisesToPay: (params = "") => req(`/promises-to-pay/${params}`),
  replayBatch: () => req("/batch/replay/", { method: "POST", body: "{}" }),
  voiceShowcase: (id) => req(`/transactions/${id}/voice-showcase/`, { method: "POST", body: "{}" }),
};
