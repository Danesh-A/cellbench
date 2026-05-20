import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DatasetDetailPage({ params }: { params: { slug: string } }) {
  const ds = await api.getDataset(params.slug);
  return (
    <article className="space-y-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">{ds.name}</h1>
        <p className="mt-2 text-slate-600">{ds.description}</p>
        <div className="mt-3 flex gap-2">
          {ds.organism && <span className="pill">{ds.organism}</span>}
          {ds.modality && <span className="pill">{ds.modality}</span>}
        </div>
      </header>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Tile label="Cells" value={ds.n_cells?.toLocaleString() ?? "—"} />
        <Tile label="Genes" value={ds.n_genes?.toLocaleString() ?? "—"} />
        <Tile label="Storage" value={ds.storage_uri} mono />
        <Tile label="Registered" value={new Date(ds.created_at).toLocaleDateString()} />
      </section>

      <section className="card">
        <h2 className="mb-2 font-semibold">Metadata</h2>
        <pre className="overflow-auto text-xs text-slate-700">
          {JSON.stringify(ds.extra, null, 2)}
        </pre>
      </section>
    </article>
  );
}

function Tile(props: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="card">
      <p className="text-xs uppercase tracking-wide text-slate-500">{props.label}</p>
      <p className={`mt-1 ${props.mono ? "truncate font-mono text-sm" : "text-lg font-semibold"}`}>
        {props.value}
      </p>
    </div>
  );
}
