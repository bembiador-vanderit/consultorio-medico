import axios from "axios";

export const ACCESS_TOKEN_KEY = "consultorio_access_token";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1",
});

export function setAccessToken(token: string | null) {
  if (token) {
    localStorage.setItem(ACCESS_TOKEN_KEY, token);
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    delete api.defaults.headers.common.Authorization;
  }
}

export function restoreAccessToken() {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  if (token) api.defaults.headers.common.Authorization = `Bearer ${token}`;
  return token;
}
