import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ChallengeDetailPage({ params }: { params: { slug: string } }) {
  const [challenge, leaderboard] = await Promise.all([
    api.getChallenge(params.slug),
    api.leaderboard(params.slug),
  ]);

  return (
    <div className="space-y-10">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{challenge.title}</h1>
          <p className="mt-2 text-slate-600">
            Metric: <code className="font-mono">{challenge.metric}</code>
            {challenge.deadline && (
              <> · Deadline {new Date(challenge.deadline).toLocaleString()}</>
            )}
          </p>
        </div>
        {challenge.is_open && (
          <Link href={`/challenges/${challenge.slug}/submit`} className="btn-primary">
            Submit prediction
          </Link>
        )}
      </header>

      <section className="card">
        <h2 className="mb-3 font-semibold">Description</h2>
        <pre className="whitespace-pre-wrap text-sm text-slate-700">
          {challenge.description_md}
        </pre>
      </section>

      <section>
        <h2 className="mb-3 font-semibold">Leaderboard</h2>
        <div className="overflow-hidden rounded-lg border border-slate-200">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Rank</th>
                <th className="px-4 py-2">User</th>
                <th className="px-4 py-2">Model</th>
                <th className="px-4 py-2 text-right">Score</th>
                <th className="px-4 py-2">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {leaderboard.map((row) => (
                <tr key={row.submission_id}>
                  <td className="px-4 py-2 font-semibold">{row.rank}</td>
                  <td className="px-4 py-2">{row.user_email}</td>
                  <td className="px-4 py-2 text-slate-600">
                    {row.model_name ? `${row.model_name} @ ${row.model_version}` : "—"}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">
                    {row.score.toFixed(4)}
                  </td>
                  <td className="px-4 py-2 text-slate-500">
                    {new Date(row.scored_at).toLocaleString()}
                  </td>
                </tr>
              ))}
              {leaderboard.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-slate-500">
                    No scored submissions yet. Be the first!
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
