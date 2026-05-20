import Link from "next/link";
import { api, type Dataset } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DatasetsPage({
  searchParams,
}: {
  searchParams: { q?: string; organism?: string; modality?: string };
}) {
  const datasets = await api.listDatasets(searchParams);
  return (
    <div className="space-y-8">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Data Catalog</h1>
          <p className="mt-1 text-slate-600">
            Browse single-cell datasets registered in the platform.
          </p>
        </div>
        <form className="flex gap-2">
          <input
            name="q"
            defaultValue={searchParams.q}
            placeholder="Search…"
            className="input"
          />
          <button className="btn-ghost">Filter</button>
        </form>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {datasets.map((ds) => (
          <DatasetCard key={ds.id} ds={ds} />
        ))}
        {datasets.length === 0 && (
          <p className="text-slate-500">No datasets match those filters yet.</p>
        )}
      </div>
    </div>
  );
}

function DatasetCard({ ds }: { ds: Dataset }) {
  return (
    <Link href={`/datasets/${ds.slug}`} className="card hover:border-accent">
      <div className="flex items-start justify-between">
        <h2 className="font-semibold">{ds.name}</h2>
        {ds.modality && <span className="pill">{ds.modality}</span>}
      </div>
      <p className="mt-2 line-clamp-2 text-sm text-slate-600">{ds.description}</p>
      <dl className="mt-4 grid grid-cols-3 gap-2 text-xs text-slate-500">
        <Stat label="organism" value={ds.organism ?? "—"} />
        <Stat label="cells" value={ds.n_cells?.toLocaleString() ?? "—"} />
        <Stat label="genes" value={ds.n_genes?.toLocaleString() ?? "—"} />
      </dl>
    </Link>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="uppercase tracking-wide">{label}</dt>
      <dd className="text-slate-800">{value}</dd>
    </div>
  );
}
