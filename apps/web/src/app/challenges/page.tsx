import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ChallengesPage() {
  const challenges = await api.listChallenges();
  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Challenges</h1>
        <p className="mt-1 text-slate-600">
          Active and past benchmarks. Sign in to submit predictions.
        </p>
      </header>

      <ul className="space-y-3">
        {challenges.map((c) => (
          <li key={c.id}>
            <Link href={`/challenges/${c.slug}`} className="card flex items-center justify-between hover:border-accent">
              <div>
                <h2 className="font-semibold">{c.title}</h2>
                <p className="text-sm text-slate-600">Metric: {c.metric}</p>
              </div>
              <span className={c.is_open ? "pill" : "pill bg-slate-100 text-slate-600"}>
                {c.is_open ? "open" : "closed"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
