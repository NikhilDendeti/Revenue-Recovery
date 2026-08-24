// Local dev leaves VITE_API_BASE_URL unset and talks to the backend through Vite's
// dev-server proxy (relative paths — see vite.config.js). A production build, served
// from a different origin than the backend (e.g. Vercel/Netlify in front of a Render
// backend), needs the real backend origin baked in at build time instead.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export const API_ROOT = `${API_BASE_URL}/api`;

export function wsUrl(path) {
  if (API_BASE_URL) {
    return `${API_BASE_URL.replace(/^http/, "ws")}${path}`;
  }
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}${path}`;
}
