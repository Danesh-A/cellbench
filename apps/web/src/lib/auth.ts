// Tiny token store. v1 keeps the JWT in localStorage for simplicity;
// v2 should move to httpOnly cookies set by a Next.js route handler.
"use client";

const KEY = "cellbench.token";

export function saveToken(token: string): void {
  if (typeof window !== "undefined") localStorage.setItem(KEY, token);
}

export function loadToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(KEY);
}

export function clearToken(): void {
  if (typeof window !== "undefined") localStorage.removeItem(KEY);
}
