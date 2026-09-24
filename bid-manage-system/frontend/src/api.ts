import type { AdminDashboard, BidderDashboard, Job, Page, Profile, User } from "./types";

const TOKEN_KEY = "bidflow_token";
export const authStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = authStore.get();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && init.body != null) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers });
  if (response.status === 401) authStore.clear();
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join(", ") : detail || "Request failed");
  }
  return response.json();
}

export const api = {
  login: (identity: string, password: string) => request<{token: string; user: User}>("/api/auth/login", { method: "POST", body: JSON.stringify({ identity, password }) }),
  me: () => request<User>("/api/auth/me"),
  changePassword: (current_password: string, new_password: string) => request<{ok: boolean}>("/api/auth/password", { method: "POST", body: JSON.stringify({ current_password, new_password }) }),
  profiles: (params: URLSearchParams) => request<Page<Profile>>(`/api/profiles?${params}`),
  profileOptions: () => request<Profile[]>("/api/profiles/options"),
  saveProfile: (id: number | null, body: unknown) => request<Profile>(id ? `/api/profiles/${id}` : "/api/profiles", { method: id ? "PUT" : "POST", body: JSON.stringify(body) }),
  deleteProfile: (id: number) => request(`/api/profiles/${id}`, { method: "DELETE" }),
  uploadResume: (id: number, file: File) => { const body = new FormData(); body.append("file", file); return request<Profile>(`/api/profiles/${id}/resume`, { method: "POST", body }); },
  users: (params: URLSearchParams) => request<Page<User>>(`/api/users?${params}`),
  saveUser: (id: number | null, body: unknown) => request<User>(id ? `/api/users/${id}` : "/api/users", { method: id ? "PUT" : "POST", body: JSON.stringify(body) }),
  deleteUser: (id: number) => request(`/api/users/${id}`, { method: "DELETE" }),
  jobs: (params: URLSearchParams) => request<Page<Job>>(`/api/jobs?${params}`),
  saveJob: (id: number | null, body: unknown) => request<Job>(id ? `/api/jobs/${id}` : "/api/jobs", { method: id ? "PUT" : "POST", body: JSON.stringify(body) }),
  updateBidderJob: (id: number, body: unknown) => request<Job>(`/api/jobs/${id}/bidder`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteJob: (id: number) => request(`/api/jobs/${id}`, { method: "DELETE" }),
  bulkJobs: (profile_id: number, text: string) => request<{created: number; errors: string[]}>("/api/jobs/bulk", { method: "POST", body: JSON.stringify({ profile_id, text }) }),
  bidderDashboard: (profileId: number | undefined, dateFrom: string, dateTo: string) => request<BidderDashboard>(`/api/dashboard/bidder?date_from=${dateFrom}&date_to=${dateTo}${profileId ? `&profile_id=${profileId}` : ""}`),
  adminDashboard: (dateFrom: string, dateTo: string) => request<AdminDashboard>(`/api/dashboard/admin?date_from=${dateFrom}&date_to=${dateTo}`),
};
