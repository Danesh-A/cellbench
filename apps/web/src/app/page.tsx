import Link from "next/link";
import type { Route } from "next";

export default function HomePage() {
  return (
    <div className="space-y-16">
      <section className="space-y-4">
        <span className="pill">Single-cell · perturbation prediction</span>
        <h1 className="text-4xl font-semibold tracking-tight">
          A benchmarking platform for virtual cell models.
        </h1>
        <p className="max-w-2xl text-slate-600">
          CellBench is a self-hosted Virtual Cell Challenge: register
          datasets, define benchmarks, push models to a registry, submit
          predictions, and watch a live leaderboard.
        </p>
        <div className="flex gap-3">
          <Link href="/challenges" className="btn-primary">Browse challenges</Link>
          <Link href="/datasets" className="btn-ghost">Explore the catalog</Link>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <FeatureCard
          title="Data Catalog"
          body="Browse h5ad / AnnData datasets with faceted search across organism, modality, and metadata."
          href="/datasets"
        />
        <FeatureCard
          title="Challenges & Leaderboard"
          body="Open benchmarks with held-out splits, automated scoring, and a live ranked leaderboard."
          href="/challenges"
        />
        <FeatureCard
          title="Model Registry"
          body="Track every training run as a model_version: parameters, framework, git SHA, linked submissions."
          href="/models"
        />
      </section>
    </div>
  );
}

function FeatureCard(props: { title: string; body: string; href: Route }) {
  return (
    <Link href={props.href} className="card hover:border-accent">
      <h3 className="font-semibold">{props.title}</h3>
      <p className="mt-2 text-sm text-slate-600">{props.body}</p>
    </Link>
  );
}
