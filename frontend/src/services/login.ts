import { AxiosError } from "axios";
import { api, setAccessToken } from "./api";
import type { User } from "../types/user";

export type LoginCredentials = { email: string; password: string };

/** Existing login contract: JSON credentials, in-memory bearer, then real profile. */
export async function authenticate(credentials: LoginCredentials): Promise<User> {
  try {
    const response = await api.post<{ access_token: string }>("/auth/login", credentials);
    setAccessToken(response.data.access_token);
    const profile = await api.get<User>("/auth/me");
    return profile.data;
  } catch (reason) {
    setAccessToken(null);
    // Never log Axios errors here: request config can contain the password/token.
    throw reason;
  }
}

export function loginErrorMessage(reason: unknown): string {
  // The API deliberately returns the same 401 for invalid and inactive accounts.
  return reason instanceof AxiosError && reason.response?.status === 401
    ? "Correo o contraseña incorrectos."
    : "No fue posible iniciar sesión. Intente nuevamente.";
}
