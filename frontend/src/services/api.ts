import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1",
  withCredentials: true,
});

export function setAccessToken(token: string | null) {
  if (token) api.defaults.headers.common.Authorization = `Bearer ${token}`;
  else delete api.defaults.headers.common.Authorization;
}

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
