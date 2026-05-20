"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Model } from "@/lib/api";
import { loadToken } from "@/lib/auth";

export default function ModelsPage() {
  const router = useRouter();
  const [models, setModels] = useState<Model[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    const token = loadToken();
    if (!token) {
      router.push("/login");
      return;
    }
    api.listModels(token).then(setModels);
  }, [router]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const token = loadToken();
    if (!token) return;
    const m = await api.createModel(token, { name, description });
    setModels([m, ...models]);
    setName("");
    setDescription("");
  }

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Model registry</h1>
        <p className="text-slate-600">
          Register the models you submit. Each version captures parameters,
          framework, and git SHA — and links back to every submission it
          produced.
        </p>
      </header>

      <form onSubmit={create} className="card space-y-3">
        <h2 className="font-semibold">Register a new model</h2>
        <input
          className="input"
          placeholder="Name (e.g. scGPT-baseline)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <input
          className="input"
          placeholder="Short description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <button className="btn-primary">Create</button>
      </form>

      <section>
        <h2 className="mb-3 font-semibold">Your models</h2>
        <ul className="space-y-3">
          {models.map((m) => (
            <li key={m.id} className="card">
              <div className="flex items-baseline justify-between">
                <h3 className="font-semibold">{m.name}</h3>
                <span className="text-xs text-slate-500">
                  {new Date(m.created_at).toLocaleDateString()}
                </span>
              </div>
              {m.description && (
                <p className="mt-1 text-sm text-slate-600">{m.description}</p>
              )}
            </li>
          ))}
          {models.length === 0 && (
            <p className="text-slate-500">No models yet.</p>
          )}
        </ul>
      </section>
    </div>
  );
}
