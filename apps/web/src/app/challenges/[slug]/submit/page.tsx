"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, type Challenge } from "@/lib/api";
import { loadToken } from "@/lib/auth";

export default function SubmitPage() {
  const router = useRouter();
  const params = useParams<{ slug: string }>();
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getChallenge(params.slug).then(setChallenge).catch((e) => setError(e.message));
  }, [params.slug]);

  async function submit() {
    setError(null);
    const token = loadToken();
    if (!token) {
      router.push("/login");
      return;
    }
    if (!file || !challenge) return;
    if (!file.name.endsWith(".h5ad")) {
      setError("File must end in .h5ad");
      return;
    }

    try {
      setStatus("creating submission");
      const { submission_id, upload_url } = await api.createSubmission(token, {
        challenge_id: challenge.id,
        filename: file.name,
      });

      setStatus("uploading");
      const put = await fetch(upload_url, {
        method: "PUT",
        body: file,
        headers: { "Content-Type": "application/octet-stream" },
      });
      if (!put.ok) throw new Error(`upload failed: ${put.status}`);

      setStatus("queuing");
      await api.completeSubmission(token, submission_id);

      setStatus("queued");
      router.push("/dashboard");
    } catch (e) {
      setError((e as Error).message);
      setStatus("error");
    }
  }

  if (!challenge) return <p className="text-slate-600">Loading…</p>;

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">
        Submit to {challenge.title}
      </h1>
      <p className="text-sm text-slate-600">
        Drop an <code className="font-mono">.h5ad</code> file containing your
        predictions on the held-out perturbations.
      </p>

      <label className="card flex cursor-pointer flex-col items-center justify-center border-dashed py-12 text-center">
        <input
          type="file"
          accept=".h5ad"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <span className="font-medium">{file?.name ?? "Click to choose .h5ad"}</span>
        {file && (
          <span className="mt-1 text-xs text-slate-500">
            {(file.size / 1024 / 1024).toFixed(1)} MB
          </span>
        )}
      </label>

      {error && <p className="text-sm text-red-600">{error}</p>}
      <p className="text-xs text-slate-500">Status: {status}</p>

      <button className="btn-primary w-full" onClick={submit} disabled={!file}>
        Upload &amp; queue for scoring
      </button>
    </div>
  );
}
