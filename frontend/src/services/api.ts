import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL?.trim() || "/api/v1",
  withCredentials: true,
});

let scheduleTimer: ReturnType<typeof setTimeout> | undefined;
export function setAccessToken(token: string | null) {
  clearTimeout(scheduleTimer);
  if (token) api.defaults.headers.common.Authorization = `Bearer ${token}`;
  else delete api.defaults.headers.common.Authorization;
  if (token) {
    try {
      // Display timer only. The backend independently validates the signed lease.
      const lease = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).schedule_until;
      if (typeof lease === "number") {
        const check = () => {
          const remaining = lease * 1000 - Date.now();
          if (remaining <= 0) {
            setAccessToken(null);
            window.dispatchEvent(new CustomEvent("atlas-session-expired", { detail: "Su jornada autorizada terminó. Vuelva a iniciar sesión durante su próximo horario." }));
          } else scheduleTimer = setTimeout(check, Math.min(remaining, 60_000));
        };
        check();
      }
    } catch { /* Opaque test tokens and malformed tokens are validated by the API. */ }
  }
}

api.interceptors.response.use(response => response, error => {
  if (error.response?.headers?.["x-access-schedule"] === "denied") {
    setAccessToken(null);
    window.dispatchEvent(new CustomEvent("atlas-session-expired", { detail: error.response.data?.detail }));
  }
  return Promise.reject(error);
});

export async function refreshAccessToken(): Promise<string | null> {
  try {
    const { data } = await api.post<{ access_token: string }>("/auth/refresh");
    setAccessToken(data.access_token);
    return data.access_token;
  } catch {
    setAccessToken(null);
    return null;
  }
}

export async function logoutSession() {
  try {
    await api.post("/auth/logout");
  } finally {
    setAccessToken(null);
  }
}
