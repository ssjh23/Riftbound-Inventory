import type { TokenOut } from "./types";

const TOKEN_KEY = "riftbound_token";
const USERNAME_KEY = "riftbound_username";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUsername(): string | null {
  return localStorage.getItem(USERNAME_KEY);
}

export function setToken(token: string, username: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USERNAME_KEY, username);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
}

async function authRequest<T>(url: string, body: object): Promise<T> {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail ?? `Request failed: ${resp.status}`);
  }
  return resp.json() as Promise<T>;
}

export async function login(username: string, password: string): Promise<TokenOut> {
  const data = await authRequest<TokenOut>("/api/auth/token", { username, password });
  setToken(data.access_token, data.username);
  return data;
}

export async function register(username: string, password: string): Promise<void> {
  await authRequest("/api/auth/register", { username, password });
}
