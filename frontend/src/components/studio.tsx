"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  api,
  type AnalysisView,
  type GarmentView,
  type ProductView,
  type WorkspaceView,
} from "@/lib/api";
import { AuthImage } from "@/components/auth-image";
import { AlgorithmCompare, BudgetFrontier, SynergyMatrix, UnlockRanking } from "@/components/graphs/charts";
import { Constellation } from "@/components/graphs/constellation";
import { Logo } from "@/components/logo";

async function pollJob(jobId: string) {
  for (let i = 0; i < 90; i += 1) {
    const job = await api.job(jobId);
    if (job.status === "succeeded" || job.status === "failed") return job;
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error("Job timed out waiting for the persistent worker. Confirm the worker process is running.");
}

function money(minor: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(minor / 100);
}

export function Studio() {
  const queryClient = useQueryClient();
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: () => api.workspace() });
  const garments = useQuery({ queryKey: ["garments"], queryFn: () => api.garments() });
  const products = useQuery({ queryKey: ["products"], queryFn: () => api.products() });
  const analysisId = workspace.data?.latest_analysis_id;
  const analysis = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => api.analysis(analysisId!),
    enabled: Boolean(analysisId),
  });
  const feedback = useQuery({ queryKey: ["feedback"], queryFn: () => api.feedbackSummary() });

  const [tab, setTab] = useState<"wardrobe" | "discover" | "compare" | "saved">("wardrobe");
  const [budget, setBudget] = useState(25000);
  const [occasion, setOccasion] = useState("any");
  const [footwear, setFootwear] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tryonLabel, setTryonLabel] = useState<string | null>(null);
  const [tryonAsset, setTryonAsset] = useState<string | null>(null);

  useEffect(() => {
    if (analysis.data?.budget_minor) setBudget(analysis.data.budget_minor);
  }, [analysis.data?.budget_minor]);

  const refresh = () => {
    queryClient.invalidateQueries();
  };

  const selectedGarment = garments.data?.items.find((item) => item.id === selectedId);
  const selectedProduct = products.data?.items.find((item) => item.id === selectedId);
  const result = analysis.data?.result;
  const selectedOutfit = useMemo(() => {
    if (!result || !selectedId) return null;
    return result.outfits.find((outfit) => (outfit.garment_ids as string[]).includes(selectedId) && outfit.qualified);
  }, [result, selectedId]);

  async function handleFiles(kind: "outfit" | "tryon_source" | "product", files: FileList | null) {
    if (!files) return;
    setError(null);
    try {
      for (const file of Array.from(files).slice(0, kind === "outfit" ? 15 : 1)) {
        const uploaded = await api.upload(kind, file);
        if (kind === "outfit") {
          const job = await api.extract(uploaded.id);
          const extracted = await pollJob(job.job_id);
          if (extracted.status === "failed") throw new Error(extracted.error_safe || "Extraction failed.");
        }
      }
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    }
  }

  const runAnalysis = useMutation({
    mutationFn: async () => {
      const created = await api.createAnalysis({
        occasion,
        budget_minor: budget,
        currency: workspace.data?.currency || "USD",
        footwear_required: footwear,
      });
      const done = await pollJob(created.job_id);
      if (done.status === "failed") throw new Error(done.error_safe || "Analysis failed.");
      return created.analysis_id;
    },
    onSuccess: refresh,
    onError: (err: Error) => setError(err.message),
  });

  const liveTryOn = useMutation({
    mutationFn: async () => {
      const garmentIds = selectedOutfit ? (selectedOutfit.garment_ids as string[]) : selectedId ? [selectedId] : [];
      const created = await api.tryon({
        combination_id: selectedOutfit?.combination_id,
        garment_ids: garmentIds,
        force_live: true,
      });
      const done = await pollJob(created.job_id);
      const status = await api.tryonStatus(created.tryon_id);
      if (status.status === "failed") throw new Error(status.error_safe || status.limitation || "Try-on failed.");
      return status;
    },
    onSuccess: (status) => {
      setTryonLabel(status.cache_hit ? "Cached result (labelled)" : "Live YouCam result");
      setTryonAsset(status.result_asset_id);
      refresh();
    },
    onError: (err: Error) => setError(err.message),
  });

  if (workspace.isError) {
    return <p className="p-10 text-coral">{(workspace.error as Error).message}</p>;
  }
  if (!workspace.data) return <p className="p-10 text-muted">Loading workspace…</p>;

  const empty = workspace.data.onboarding_required && !workspace.data.consent;

  return (
    <div className="min-h-screen bg-white">
      <header className="grid grid-cols-[220px_1fr_340px] items-center border-b border-[#f4f4f4] px-5 py-4">
        <Logo />
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-pink">Hot pink / the wardrobe canvas</p>
          <h1 className="text-3xl font-semibold tracking-tight">Discover what clicks in your closet.</h1>
          <p className="text-sm text-muted">Explore how a single purchase can unlock rule-qualified outfit options with clothes you already own.</p>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span>Budget for new items</span>
            <strong>{money(budget, workspace.data.currency || "USD")}</strong>
          </div>
          <input type="range" min={0} max={50000} step={500} value={budget} onChange={(event) => setBudget(Number(event.target.value))} className="w-full accent-pink" />
          <label className="flex cursor-pointer items-center justify-end gap-2 text-sm text-pink">
            <input type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={(event) => handleFiles("outfit", event.target.files)} />
            Upload outfit photos
          </label>
        </div>
      </header>

      <div className="grid grid-cols-[88px_1fr_340px]">
        <nav className="flex flex-col items-center gap-6 border-r border-[#f4f4f4] py-8 text-[11px] text-muted">
          {[
            ["wardrobe", "Wardrobe"],
            ["discover", "Discover"],
            ["compare", "Compare"],
            ["saved", "Saved"],
          ].map(([id, label]) => (
            <button key={id} onClick={() => setTab(id as typeof tab)} className={tab === id ? "text-pink" : ""}>
              {label}
            </button>
          ))}
        </nav>

        <section className="min-h-[640px] px-6 py-5">
          {error && <p className="mb-4 rounded-xl bg-pink-soft px-3 py-2 text-sm text-pink">{error}</p>}
          {empty || !workspace.data.consent ? (
            <Onboarding workspace={workspace.data} onDone={refresh} onError={setError} />
          ) : tab === "wardrobe" ? (
            <WardrobeDesk
              garments={garments.data?.items || []}
              products={products.data?.items || []}
              hasTryOn={workspace.data.has_tryon_photo}
              onRefresh={refresh}
              onError={setError}
              onUpload={handleFiles}
            />
          ) : tab === "compare" ? (
            <div className="grid gap-8 lg:grid-cols-2">
              {result ? (
                <>
                  <UnlockRanking result={result} />
                  <BudgetFrontier result={result} />
                  <AlgorithmCompare result={result} />
                </>
              ) : (
                <EmptyGraph label="Run an analysis to populate comparison charts from persisted results." />
              )}
            </div>
          ) : tab === "saved" ? (
            <FeedbackPanel analysis={analysis.data} onRefresh={refresh} />
          ) : (
            <>
              <Constellation
                garments={garments.data?.items || []}
                edges={result?.edges || []}
                selectedId={selectedId}
                onSelect={setSelectedId}
                />
              {selectedOutfit && (
                <div className="mt-4 max-w-sm rounded-2xl border border-[#f1f1f1] p-4 shadow-sm">
                  <p className="text-sm font-semibold">{selectedGarment?.display_name || "Selected look"}</p>
                  <p className="text-xs text-muted">Template {String(selectedOutfit.template)}. Compatibility is not approval.</p>
                  <button className="mt-2 text-sm text-pink" onClick={() => setTab("saved")}>
                    View outfit →
                  </button>
                </div>
              )}
            </>
          )}
        </section>

        <aside className="border-l border-[#f4f4f4] p-5">
          {selectedProduct || selectedGarment ? (
            <SelectedCard
              garment={selectedGarment}
              product={selectedProduct}
              result={result}
            />
          ) : (
            <p className="text-sm text-muted">Select a garment or candidate to inspect evidence. Nothing is prefilled.</p>
          )}
          <div className="mt-6">
            <p className="text-sm font-semibold">Try it on</p>
            <p className="text-xs text-muted">Live YouCam only. Cached results stay labelled. Crops used for counting may be unsuitable VTO references.</p>
            {tryonAsset && (
              <div className="mt-3">
                <AuthImage assetId={tryonAsset} alt="Live try-on result" className="h-48 w-full rounded-2xl object-cover" />
                <p className="mt-1 text-[11px] text-pink">{tryonLabel}</p>
              </div>
            )}
            <button
              onClick={() => liveTryOn.mutate()}
              disabled={liveTryOn.isPending}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-full bg-pink py-3 text-sm font-medium text-white disabled:opacity-50"
            >
              {liveTryOn.isPending ? "Submitting live task…" : "Generate live try-on"}
            </button>
          </div>
        </aside>
      </div>

      <footer className="grid grid-cols-[1fr_340px] border-t border-[#f4f4f4]">
        <div className="p-5">
          {result ? <SynergyMatrix result={result} /> : <EmptyGraph label="Synergy matrix waits for a persisted analysis." />}
          {feedback.data && (
            <p className="mt-3 text-xs text-muted">
              Approvals {feedback.data.approved} / rejections {feedback.data.rejected} (denominator {feedback.data.denominator}).
            </p>
          )}
        </div>
        <div className="border-l border-[#f4f4f4] p-5">
          <h3 className="text-sm font-semibold">Shop recommended additions</h3>
          <p className="mb-3 text-xs text-muted">Only items you added. No fabricated catalogue.</p>
          <div className="grid grid-cols-2 gap-3">
            {products.data?.items.map((item) => (
              <button key={item.id} onClick={() => setSelectedId(item.id)} className="text-left">
                <AuthImage assetId={item.image_asset_id} alt={item.title} className="h-28 w-full rounded-xl object-cover" />
                <p className="mt-1 text-xs font-medium">{item.title}</p>
                <p className="text-xs text-muted">{money(item.price_minor, item.currency)}</p>
              </button>
            ))}
          </div>
          <div className="mt-4 flex gap-2">
            <select value={occasion} onChange={(event) => setOccasion(event.target.value)} className="flex-1 rounded-xl border border-[#eee] px-2 py-2 text-sm">
              <option value="any">Any occasion</option>
              <option value="casual">Casual</option>
              <option value="smart_casual">Smart casual</option>
              <option value="office">Office</option>
              <option value="evening">Evening</option>
            </select>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={footwear} onChange={(event) => setFootwear(event.target.checked)} />
              Require footwear
            </label>
          </div>
          <button onClick={() => runAnalysis.mutate()} disabled={runAnalysis.isPending} className="mt-3 w-full rounded-full bg-ink py-3 text-sm text-white">
            {runAnalysis.isPending ? "Computing exact basket…" : "Compute rankings"}
          </button>
          <button
            className="mt-4 text-[11px] text-pink"
            onClick={async () => {
              await api.deleteWorkspace();
              refresh();
            }}
          >
            Start over
          </button>
        </div>
      </footer>
    </div>
  );
}

function EmptyGraph({ label }: { label: string }) {
  return <div className="rounded-2xl border border-dashed border-[#eee] p-8 text-sm text-muted">{label}</div>;
}

function SelectedCard({
  garment,
  product,
  result,
}: {
  garment?: GarmentView;
  product?: ProductView;
  result?: AnalysisView["result"];
}) {
  const title = product?.title || garment?.display_name || "";
  const standalone = result?.standalone.find((row) => row.product_id === (product?.id || garment?.id));
  return (
    <div>
      <AuthImage
        assetId={product?.image_asset_id || garment?.crop_asset_id}
        alt={title}
        className="h-56 w-full rounded-2xl object-cover"
      />
      <h2 className="mt-4 text-xl font-semibold">{title}</h2>
      {product && <p className="text-lg">{money(product.price_minor, product.currency)}</p>}
      <p className="mt-2 text-sm text-muted">
        {garment?.colour || product?.category}. Analysis eligibility is separate from YouCam eligibility.
      </p>
      {standalone && (
        <ul className="mt-4 space-y-1 text-sm">
          <li>Standalone yield: {String(standalone.standalone_f)}</li>
          <li>Basket-conditional: {String(standalone.basket_conditional_f)}</li>
        </ul>
      )}
      {product?.cart_item_id && (
        <div className="mt-4 flex gap-2 text-xs">
          <button className="rounded-full border px-3 py-1" onClick={() => api.patchCart(product.cart_item_id!, { pinned: !product.pinned })}>
            {product.pinned ? "Unpin" : "Pin this item"}
          </button>
          <button className="rounded-full border px-3 py-1" onClick={() => api.patchCart(product.cart_item_id!, { excluded: !product.excluded })}>
            {product.excluded ? "Include" : "Exclude"}
          </button>
        </div>
      )}
    </div>
  );
}

function Onboarding({
  workspace,
  onDone,
  onError,
}: {
  workspace: WorkspaceView;
  onDone: () => void;
  onError: (message: string) => void;
}) {
  async function grant() {
    try {
      await api.consent();
      onDone();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Consent failed.");
    }
  }
  return (
    <div className="mx-auto max-w-xl py-16 text-center">
      <h2 className="text-3xl font-semibold">Start with your own photographs</h2>
      <p className="mt-3 text-muted">
        External image processing (Gemini extraction and optional YouCam try-on) needs explicit consent. There is no
        preloaded wardrobe, catalogue, or generated preview.
      </p>
      {!workspace.consent && (
        <button onClick={grant} className="mt-6 rounded-full bg-pink px-6 py-3 text-white">
          I consent to external image processing
        </button>
      )}
    </div>
  );
}

function WardrobeDesk({
  garments,
  products,
  hasTryOn,
  onRefresh,
  onError,
  onUpload,
}: {
  garments: GarmentView[];
  products: ProductView[];
  hasTryOn: boolean;
  onRefresh: () => void;
  onError: (message: string) => void;
  onUpload: (kind: "outfit" | "tryon_source" | "product", files: FileList | null) => Promise<void>;
}) {
  const [mergeTarget, setMergeTarget] = useState<string>("");
  const [draft, setDraft] = useState<Record<string, string>>({
    title: "",
    price_major: "",
    currency: "USD",
    category: "top",
    colour_family: "",
    pattern_family: "solid",
    formality_min: "30",
    formality_max: "70",
  });
  const [productFile, setProductFile] = useState<File | null>(null);

  async function confirm(item: GarmentView) {
    try {
      await api.patchGarment(item.id, {
        display_name: item.display_name,
        category: item.category,
        colour_family: item.colour_family || item.colour,
        pattern_family: item.pattern_family || "solid",
        formality_min: item.formality_min ?? 30,
        formality_max: item.formality_max ?? 70,
        confirm: true,
      });
      onRefresh();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not confirm garment.");
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap gap-3 text-sm">
        <label className="rounded-full bg-pink-soft px-4 py-2 text-pink">
          <input type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={(event) => onUpload("outfit", event.target.files)} />
          Add outfit photos
        </label>
        <label className="rounded-full border border-[#eee] px-4 py-2">
          <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(event) => onUpload("tryon_source", event.target.files)} />
          {hasTryOn ? "Replace try-on photo" : "Upload try-on photo"}
        </label>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {garments
          .filter((item) => item.source_kind === "wardrobe")
          .map((item) => (
            <article key={item.id} className="rounded-2xl border border-[#f1f1f1] p-3">
              <AuthImage assetId={item.crop_asset_id} alt={item.display_name} className="h-40 w-full rounded-xl object-cover" />
              <input
                className="mt-2 w-full text-sm font-medium"
                defaultValue={item.display_name}
                onBlur={(event) => api.patchGarment(item.id, { display_name: event.target.value }).then(onRefresh)}
              />
              <p className="text-xs text-muted">
                {item.category} · {item.status}
                {item.needs_review ? " · needs review" : ""}
              </p>
              <div className="mt-2 flex gap-2">
                {item.status !== "confirmed" && (
                  <button className="text-xs text-pink" onClick={() => confirm(item)}>
                    Confirm
                  </button>
                )}
                <button className="text-xs text-muted" onClick={() => setMergeTarget(item.id)}>
                  Merge into this
                </button>
              </div>
            </article>
          ))}
      </div>
      {mergeTarget && (
        <p className="text-xs text-muted">
          Merges require confirmation and never run from colour alone. Select another card then
          <button
            className="ml-1 text-pink"
            onClick={async () => {
              const others = garments.filter((item) => item.id !== mergeTarget && item.status !== "merged").map((item) => item.id);
              if (others[0]) await api.merge(mergeTarget, [others[0]]);
              setMergeTarget("");
              onRefresh();
            }}
          >
            confirm merge with the next garment
          </button>
          .
        </p>
      )}
      <form
        className="grid gap-3 rounded-2xl border border-[#f1f1f1] p-4 md:grid-cols-2"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!productFile) {
            onError("Upload-and-enter-price is the supported production path. Attach the product image.");
            return;
          }
          try {
            await api.createProduct(draft, productFile);
            setDraft({ title: "", price_major: "", currency: draft.currency, category: "top" });
            setProductFile(null);
            onRefresh();
          } catch (err) {
            onError(err instanceof Error ? err.message : "Product create failed.");
          }
        }}
      >
        <h3 className="md:col-span-2 text-sm font-semibold">Add a real cart candidate</h3>
        <input className="rounded-xl border border-[#eee] px-3 py-2" placeholder="Title" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} required />
        <input className="rounded-xl border border-[#eee] px-3 py-2" placeholder="Price (major units)" value={draft.price_major} onChange={(event) => setDraft({ ...draft, price_major: event.target.value })} required />
        <input className="rounded-xl border border-[#eee] px-3 py-2" placeholder="USD" value={draft.currency} onChange={(event) => setDraft({ ...draft, currency: event.target.value })} />
        <select className="rounded-xl border border-[#eee] px-3 py-2" value={draft.category} onChange={(event) => setDraft({ ...draft, category: event.target.value })}>
          <option value="top">Top</option>
          <option value="bottom">Bottom</option>
          <option value="dress">Dress</option>
          <option value="outerwear">Outerwear</option>
          <option value="footwear">Footwear</option>
        </select>
        <input className="rounded-xl border border-[#eee] px-3 py-2" placeholder="Colour family (required for analysis)" value={draft.colour_family} onChange={(event) => setDraft({ ...draft, colour_family: event.target.value })} />
        <input className="rounded-xl border border-[#eee] px-3 py-2" placeholder="Pattern family" value={draft.pattern_family} onChange={(event) => setDraft({ ...draft, pattern_family: event.target.value })} />
        <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setProductFile(event.target.files?.[0] || null)} />
        <button className="rounded-full bg-pink px-4 py-2 text-sm text-white">Save candidate</button>
        <p className="md:col-span-2 text-xs text-muted">
          {products.length} / 10 candidates. Shipping and tax are excluded unless you mark them included. URL fetch only reads public HTTPS JSON-LD; otherwise enter price manually.
        </p>
      </form>
    </div>
  );
}

function FeedbackPanel({
  analysis,
  onRefresh,
}: {
  analysis?: AnalysisView;
  onRefresh: () => void;
}) {
  const outfits = analysis?.result?.outfits.filter((item) => item.qualified) || [];
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {outfits.map((outfit) => (
        <div key={String(outfit.combination_id)} className="rounded-2xl border border-[#f1f1f1] p-4">
          <p className="text-sm font-medium">Look {String(outfit.combination_id)}</p>
          <p className="text-xs text-muted">{String(outfit.template)} · cluster {String(outfit.cluster_id)}</p>
          <div className="mt-3 flex gap-2">
            <button
              className="rounded-full bg-green px-3 py-1 text-xs text-white"
              onClick={() =>
                api.feedback({
                  analysis_id: analysis!.id,
                  target_kind: "outfit",
                  target_id: outfit.combination_id,
                  verdict: "approve",
                }).then(onRefresh)
              }
            >
              Approve
            </button>
            <button
              className="rounded-full bg-coral px-3 py-1 text-xs text-white"
              onClick={() =>
                api.feedback({
                  analysis_id: analysis!.id,
                  target_kind: "outfit",
                  target_id: outfit.combination_id,
                  verdict: "reject",
                }).then(onRefresh)
              }
            >
              Reject
            </button>
          </div>
        </div>
      ))}
      {!outfits.length && <EmptyGraph label="Qualified looks from a persisted analysis appear here." />}
    </div>
  );
}
