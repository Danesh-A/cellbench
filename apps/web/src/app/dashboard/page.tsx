"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Submission, type User } from "@/lib/api";
import { loadToken } from "@/lib/auth";

const STATUS_COLORS: Record<Submission["status"], string> = {
  pending_upload: "bg-slate-100 text-slate-600",
  queued: "bg-amber-100 text-amber-800",
  scoring: "bg-blue-100 text-blue-800",
  scored: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
};

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [subs, setSubs] = useState<Submission[]>([]);

  useEffect(() => {
    const token = loadToken();
    if (!token) {
      router.push("/login");
      return;
    }
    Promise.all([api.me(token), api.mySubmissions(token)])
      .then(([u, s]) => {
        setUser(u);
        setSubs(s);
      })
      .catch(() => router.push("/login"));
  }, [router]);

  if (!user) return <p className="text-slate-600">Loading…</p>;

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">
          Welcome, {user.full_name || user.email}
        </h1>
        <p className="text-slate-600">Your submissions and recent activity.</p>
      </header>

      <section>
        <h2 className="mb-3 font-semibold">Your submissions</h2>
        <div className="overflow-hidden rounded-lg border border-slate-200">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Submitted</th>
                <th className="px-4 py-2">Challenge</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Scored</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {subs.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-2">{new Date(s.submitted_at).toLocaleString()}</td>
                  <td className="px-4 py-2 font-mono text-xs">{s.challenge_id}</td>
                  <td className="px-4 py-2">
                    <span className={`pill ${STATUS_COLORS[s.status]}`}>{s.status}</span>
                  </td>
                  <td className="px-4 py-2 text-slate-500">
                    {s.scored_at ? new Date(s.scored_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
              {subs.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-slate-500">
                    No submissions yet — pick a challenge and submit your first.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
