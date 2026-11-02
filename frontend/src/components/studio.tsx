"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  api,
  type AnalysisView,
  type AssetView,
  type GarmentView,
  type ProductView,
} from "@/lib/api";
import { AuthImage } from "@/components/auth-image";
import { AlgorithmCompare, BudgetFrontier, UnlockRanking } from "@/components/graphs/charts";
import { CombinationHub } from "@/components/graphs/hub";
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

function workspaceErrorMessage(err: unknown) {
  const raw = err instanceof Error ? err.message : "The Closest Chemistry API is unreachable.";
  const text = raw.replace(/\.*$/, ".");
  if (/^cannot reach/i.test(text)) return text;
  if (/failed to fetch|networkerror|load failed/i.test(text)) {
    return "Cannot reach the Closest Chemistry API, so this closet is not saved. Set API_URL on Vercel to your Railway/Render origin, or start FastAPI on port 8000 locally.";
  }
  return text;
}

type Tab = "closet" | "bag" | "saved" | "how";

type PendingPhoto = {
  key: string;
  name: string;
  preview?: string;
  assetId?: string;
  status: "uploading" | "extracting" | "ready" | "error";
  message?: string;
};

export function Studio() {
  const queryClient = useQueryClient();
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: () => api.workspace() });
  const garments = useQuery({ queryKey: ["garments"], queryFn: () => api.garments() });
  const products = useQuery({ queryKey: ["products"], queryFn: () => api.products() });
  const outfitPhotos = useQuery({ queryKey: ["assets", "outfit"], queryFn: () => api.assets("outfit") });
  const analysisId = workspace.data?.latest_analysis_id;
  const analysis = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => api.analysis(analysisId!),
    enabled: Boolean(analysisId),
  });
  const feedback = useQuery({ queryKey: ["feedback"], queryFn: () => api.feedbackSummary() });

  const [tab, setTab] = useState<Tab>("closet");
  const [closetFilter, setClosetFilter] = useState<"all" | "top" | "bottom" | "dress" | "outerwear" | "footwear">("all");
  const [centerMode, setCenterMode] = useState<"connections" | "cards">("connections");
  const [budget, setBudget] = useState(25000);
  const [occasion, setOccasion] = useState("any");
  const [footwear, setFootwear] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tryonLabel, setTryonLabel] = useState<string | null>(null);
  const [tryonAsset, setTryonAsset] = useState<string | null>(null);
  const [showPurchase, setShowPurchase] = useState(false);
  const [pendingPhotos, setPendingPhotos] = useState<PendingPhoto[]>([]);

  const refresh = () => queryClient.invalidateQueries();
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
    const selected = Array.from(files).slice(0, kind === "outfit" ? 15 : 1);
    try {
      for (const file of selected) {
        const key = `${file.name}-${file.size}-${file.lastModified}-${Math.random()}`;
        const preview = URL.createObjectURL(file);
        if (kind === "outfit") {
          setPendingPhotos((current) => [
            { key, name: file.name, preview, status: "uploading" },
            ...current,
          ]);
        }
        try {
          const uploaded = await api.upload(kind, file);
          if (kind === "outfit") {
            setPendingPhotos((current) =>
              current.map((item) =>
                item.key === key ? { ...item, assetId: uploaded.id, status: "extracting" } : item,
              ),
            );
            refresh();
            try {
              const job = await api.extract(uploaded.id);
              const extracted = await pollJob(job.job_id);
              if (extracted.status === "failed") {
                throw new Error(extracted.error_safe || "Extraction failed.");
              }
              setPendingPhotos((current) =>
                current.map((item) => (item.key === key ? { ...item, status: "ready" } : item)),
              );
            } catch (extractErr) {
              const message = extractErr instanceof Error ? extractErr.message : "Extraction failed.";
              setPendingPhotos((current) =>
                current.map((item) => (item.key === key ? { ...item, status: "error", message } : item)),
              );
              setError(message);
            }
          }
        } catch (uploadErr) {
          const message = uploadErr instanceof Error ? uploadErr.message : "Upload failed.";
          if (kind === "outfit") {
            setPendingPhotos((current) =>
              current.map((item) => (item.key === key ? { ...item, status: "error", message } : item)),
            );
          }
          throw uploadErr;
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

  const owned = (garments.data?.items || []).filter((item) => item.source_kind === "wardrobe");
  const filteredOwned =
    closetFilter === "all" ? owned : owned.filter((item) => item.category === closetFilter);
  const bag = products.data?.items || [];
  const pendingAssetIds = new Set(pendingPhotos.map((item) => item.assetId).filter(Boolean) as string[]);
  const uploadedPhotos = (outfitPhotos.data?.items || []).filter((item) => !pendingAssetIds.has(item.id));
  const qualifiedLooks = (result?.outfits || []).filter((item) => item.qualified).slice(0, 6);

  const closetFilters = useMemo(() => {
    const chips: Array<{ id: typeof closetFilter; label: string }> = [
      { id: "all", label: "All" },
      { id: "top", label: "Tops" },
      { id: "bottom", label: "Bottoms" },
    ];
    if (owned.some((item) => item.category === "dress")) chips.push({ id: "dress", label: "Dresses" });
    if (owned.some((item) => item.category === "outerwear")) chips.push({ id: "outerwear", label: "Outerwear" });
    if (owned.some((item) => item.category === "footwear")) chips.push({ id: "footwear", label: "Shoes" });
    return chips;
  }, [owned]);

  return (
    <div className="min-h-screen bg-cream">
      <header className="flex items-center justify-between px-6 py-4 lg:px-8">
        <Logo />
        <nav className="hidden items-center gap-8 text-sm text-muted md:flex">
          {(
            [
              ["closet", "Your closet"],
              ["bag", "Shopping bag"],
              ["saved", "Saved looks"],
              ["how", "How it works"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={tab === id ? "font-medium text-ink underline decoration-pink decoration-2 underline-offset-[10px]" : "hover:text-ink"}
            >
              {label}
            </button>
          ))}
        </nav>
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#f3d0c4] text-xs font-medium text-ink">
          You
        </span>
      </header>

      <section className="flex flex-wrap items-end justify-between gap-4 px-6 pb-5 lg:px-8">
        <div>
          <h1 className="font-display text-[40px] leading-tight font-semibold tracking-tight text-ink">
            Find your next great combination.
          </h1>
          <p className="mt-1 text-sm text-muted">See what each purchase adds to the clothes you already own.</p>
        </div>
        <div className="flex gap-3">
          <label className="cursor-pointer rounded-full bg-pink px-5 py-2.5 text-sm font-medium text-white shadow-[0_8px_20px_rgba(255,45,139,0.28)]">
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              multiple
              className="hidden"
              onChange={(event) => {
                handleFiles("outfit", event.target.files);
                event.target.value = "";
              }}
            />
            + Add outfit photos
          </label>
          <button
            onClick={() => {
              setTab("bag");
              setShowPurchase(true);
            }}
            className="inline-flex items-center gap-2 rounded-full border border-pink bg-white px-5 py-2.5 text-sm font-medium text-pink"
          >
            <BagIcon />
            Add a purchase
          </button>
        </div>
      </section>

      {error && <p className="mx-8 mb-4 rounded-2xl bg-pink-soft px-4 py-2 text-sm text-pink">{error}</p>}
      {workspace.isError && (
        <p className="mx-8 mb-4 rounded-2xl bg-pink-soft px-4 py-2 text-sm text-pink">
          {workspaceErrorMessage(workspace.error)}
        </p>
      )}

      {workspace.data && !workspace.data.consent ? (
        <Onboarding onDone={refresh} onError={setError} />
      ) : tab === "how" ? (
        <HowItWorks />
      ) : tab === "saved" ? (
        <div className="px-6 pb-10 lg:px-8">
          <FeedbackPanel analysis={analysis.data} onRefresh={refresh} />
          {feedback.data && (
            <p className="mt-4 text-xs text-muted">
              Approvals {feedback.data.approved} / rejections {feedback.data.rejected} (denominator {feedback.data.denominator}).
            </p>
          )}
        </div>
      ) : tab === "bag" ? (
        <div className="grid gap-6 px-6 pb-10 lg:grid-cols-[1fr_360px] lg:px-8">
          <BagGrid products={bag} onSelect={setSelectedId} />
          <PurchaseForm
            open={showPurchase || bag.length === 0}
            products={bag}
            onRefresh={refresh}
            onError={setError}
            budget={budget}
            setBudget={setBudget}
            occasion={occasion}
            setOccasion={setOccasion}
            footwear={footwear}
            setFootwear={setFootwear}
            currency={workspace.data?.currency || "USD"}
            analyzing={runAnalysis.isPending}
            onAnalyze={() => runAnalysis.mutate()}
          />
        </div>
      ) : (
        <>
          <div className="grid gap-5 px-6 pb-5 lg:px-8 xl:grid-cols-[232px_minmax(0,1fr)_292px]">
            <aside className="space-y-5">
              <div>
                <h2 className="mb-3 font-display text-[22px] font-semibold tracking-tight">Your closet</h2>
                <div className="mb-3 flex flex-wrap gap-1">
                  {closetFilters.map((chip) => (
                    <button
                      key={chip.id}
                      onClick={() => setClosetFilter(chip.id)}
                      className={`rounded-full px-3 py-1 text-xs ${closetFilter === chip.id ? "bg-pink text-white" : "bg-white text-muted"}`}
                    >
                      {chip.label}
                    </button>
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  {closetFilter === "all" &&
                    pendingPhotos.map((item) => (
                      <article key={item.key} className="rounded-[22px] bg-white p-2 shadow-[0_6px_18px_rgba(40,20,20,0.04)]">
                        <AuthImage
                          src={item.preview}
                          assetId={item.assetId}
                          alt={item.name}
                          className="h-[88px] w-full rounded-2xl object-cover"
                        />
                        <p className="mt-1.5 truncate text-center text-[11px]">{item.name}</p>
                        <p className="text-center text-[10px] text-pink">
                          {item.status === "uploading"
                            ? "Uploading…"
                            : item.status === "extracting"
                              ? "Finding garments…"
                              : item.status === "error"
                                ? item.message || "Could not extract"
                                : "Uploaded"}
                        </p>
                      </article>
                    ))}
                  {closetFilter === "all" &&
                    uploadedPhotos.map((item: AssetView) => (
                      <article key={item.id} className="rounded-[22px] bg-white p-2 shadow-[0_6px_18px_rgba(40,20,20,0.04)]">
                        <AuthImage assetId={item.id} alt={item.original_filename || "Outfit photo"} className="h-[88px] w-full rounded-2xl object-cover" />
                        <p className="mt-1.5 truncate text-center text-[11px]">{item.original_filename || "Outfit photo"}</p>
                        <p className="text-center text-[10px] text-muted">Uploaded photo</p>
                      </article>
                    ))}
                  {filteredOwned.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => setSelectedId(item.id)}
                      className={`rounded-[22px] bg-white p-2 text-left shadow-[0_6px_18px_rgba(40,20,20,0.04)] ${selectedId === item.id ? "ring-2 ring-pink" : ""}`}
                    >
                      <AuthImage assetId={item.crop_asset_id} alt={item.display_name} className="h-[88px] w-full rounded-2xl object-cover" />
                      <p className="mt-1.5 truncate text-center text-[11px]">{item.display_name || item.category}</p>
                      {item.status !== "confirmed" && (
                        <button
                          className="block w-full text-center text-[10px] text-pink"
                          onClick={(event) => {
                            event.stopPropagation();
                            api
                              .patchGarment(item.id, {
                                display_name: item.display_name,
                                category: item.category,
                                colour_family: item.colour_family || item.colour,
                                pattern_family: item.pattern_family || "solid",
                                formality_min: item.formality_min ?? 30,
                                formality_max: item.formality_max ?? 70,
                                confirm: true,
                              })
                              .then(refresh)
                              .catch((err: Error) => setError(err.message));
                          }}
                        >
                          Confirm
                        </button>
                      )}
                    </button>
                  ))}
                  <label className="col-span-2 flex min-h-[72px] cursor-pointer flex-col items-center justify-center rounded-[22px] border border-dashed border-pink/45 bg-white/70 text-center text-[11px] font-medium text-pink">
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      multiple
                      className="hidden"
                      onChange={(event) => {
                        handleFiles("outfit", event.target.files);
                        event.target.value = "";
                      }}
                    />
                    + Add a garment
                  </label>
                </div>
              </div>
              <div className="rounded-[28px] bg-[#fde8f1] p-4">
                <div className="mb-3 flex items-center justify-between text-sm font-semibold">
                  <span>Shopping bag</span>
                  <button className="text-muted" onClick={() => setTab("bag")} aria-label="Open shopping bag">
                    ›
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {bag.slice(0, 4).map((item) => (
                    <button key={item.id} onClick={() => setSelectedId(item.id)} className="text-left">
                      <AuthImage assetId={item.image_asset_id} alt={item.title} className="h-[72px] w-full rounded-2xl bg-white object-cover" />
                      <p className="mt-1 truncate text-center text-[11px]">{item.title}</p>
                    </button>
                  ))}
                  {!bag.length && <p className="col-span-2 text-[11px] text-muted">No candidates yet. Add a real purchase.</p>}
                </div>
                <button className="mt-3 text-[12px] font-medium text-pink" onClick={() => setTab("bag")}>
                  Compare purchases →
                </button>
              </div>
            </aside>

            <section className="rounded-[32px] bg-white p-5 shadow-[0_10px_40px_rgba(40,20,20,0.04)]">
              <div className="mb-2 flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-display text-[28px] font-semibold tracking-tight">What works together</h2>
                  <p className="text-sm text-muted">Styling suggestions</p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex rounded-full bg-cream p-1 text-xs">
                    <button onClick={() => setCenterMode("connections")} className={`rounded-full px-3 py-1 ${centerMode === "connections" ? "bg-pink text-white" : "text-muted"}`}>
                      Connections
                    </button>
                    <button onClick={() => setCenterMode("cards")} className={`rounded-full px-3 py-1 ${centerMode === "cards" ? "bg-pink text-white" : "text-muted"}`}>
                      Outfit cards
                    </button>
                  </div>
                  <div className="hidden text-[10px] text-muted lg:block">
                    <p><span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#d9d4d2]" />Owned</p>
                    <p><span className="mr-1 inline-block h-2 w-2 rounded-full bg-pink" />Considering</p>
                  </div>
                </div>
              </div>
              {centerMode === "connections" ? (
                <CombinationHub
                  garments={owned}
                  products={bag}
                  result={result}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  onSeeOutfits={() => setCenterMode("cards")}
                />
              ) : null}
              {centerMode === "connections" ? (
                <div className="mt-2">
                  <p className="mb-2 text-sm font-semibold">Complete outfit suggestions</p>
                  <OutfitCards looks={qualifiedLooks} garments={owned} products={bag} />
                  <p className="mt-3 text-center text-[11px] text-muted">Connections are suggestions. You decide what works.</p>
                </div>
              ) : (
                <OutfitCards looks={qualifiedLooks} garments={owned} products={bag} />
              )}
            </section>

            <aside className="rounded-[32px] bg-white p-4 shadow-[0_10px_40px_rgba(40,20,20,0.04)]">
              <h2 className="font-display text-[22px] font-semibold tracking-tight">Try the combination</h2>
              <div className="relative mt-3 overflow-hidden rounded-[24px] bg-cream">
                {tryonAsset ? (
                  <AuthImage assetId={tryonAsset} alt="Live try-on result" className="h-64 w-full object-cover" />
                ) : (
                  <div className="flex h-64 items-center justify-center px-4 text-center text-sm text-muted">
                    Live YouCam preview appears here after a successful task. Nothing is prefilled.
                  </div>
                )}
                {tryonLabel && (
                  <span className="absolute right-2 top-2 rounded-full bg-white/90 px-2 py-0.5 text-[10px] text-muted">
                    {tryonLabel}
                  </span>
                )}
              </div>
              {qualifiedLooks.length > 0 && (
                <div className="mt-3 flex justify-center gap-2">
                  {qualifiedLooks.slice(0, 2).map((look, index) => (
                    <button
                      key={String(look.combination_id)}
                      onClick={() => {
                        const ids = look.garment_ids as string[];
                        setSelectedId(ids.find((id) => bag.some((item) => item.id === id)) || ids[0] || null);
                      }}
                      className={`overflow-hidden rounded-2xl ${index === 0 ? "ring-2 ring-pink" : "ring-1 ring-line"}`}
                    >
                      <AuthImage
                        assetId={
                          owned.find((item) => (look.garment_ids as string[]).includes(item.id))?.crop_asset_id ||
                          bag.find((item) => (look.garment_ids as string[]).includes(item.id))?.image_asset_id
                        }
                        alt=""
                        className="h-14 w-14 object-cover"
                      />
                    </button>
                  ))}
                </div>
              )}
              <label className="mt-3 block cursor-pointer text-center text-[11px] text-pink">
                <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(event) => handleFiles("tryon_source", event.target.files)} />
                {workspace.data?.has_tryon_photo ? "Replace try-on photo" : "Upload a try-on photo"}
              </label>
              <div className="mt-4 grid grid-cols-2 gap-2 text-[11px]">
                <div>
                  <p className="mb-1 text-muted">Already yours</p>
                  <div className="flex gap-1">
                    {owned.slice(0, 3).map((item) => (
                      <AuthImage key={item.id} assetId={item.crop_asset_id} alt="" className="h-10 w-10 rounded-lg object-cover" />
                    ))}
                    {!owned.length && <span className="text-[10px] text-muted">None yet</span>}
                  </div>
                </div>
                <div>
                  <p className="mb-1 text-muted">Considering</p>
                  <div className="flex gap-1">
                    {bag.slice(0, 2).map((item) => (
                      <AuthImage key={item.id} assetId={item.image_asset_id} alt="" className="h-10 w-10 rounded-lg object-cover" />
                    ))}
                    {!bag.length && <span className="text-[10px] text-muted">None yet</span>}
                  </div>
                </div>
              </div>
              <button
                onClick={() => liveTryOn.mutate()}
                disabled={liveTryOn.isPending}
                className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-full bg-pink py-3 text-sm font-medium text-white shadow-[0_8px_20px_rgba(255,45,139,0.28)] disabled:opacity-50"
              >
                <SparkleIcon />
                {liveTryOn.isPending ? "Submitting live task…" : "Generate live try-on"}
              </button>
              <p className="mt-2 text-center text-[11px] text-muted">Preview styling, not physical fit.</p>
              <div className="mt-3 flex gap-2 text-xs">
                <button
                  className="flex-1 rounded-full border border-line py-2 disabled:opacity-40"
                  disabled={!analysis.data || !selectedOutfit}
                  onClick={() =>
                    selectedOutfit &&
                    analysis.data &&
                    api.feedback({ analysis_id: analysis.data.id, target_kind: "outfit", target_id: selectedOutfit.combination_id, verdict: "approve" }).then(refresh)
                  }
                >
                  Keep this option
                </button>
                <button
                  className="flex-1 rounded-full border border-line py-2 disabled:opacity-40"
                  disabled={!analysis.data || !selectedOutfit}
                  onClick={() =>
                    selectedOutfit &&
                    analysis.data &&
                    api.feedback({ analysis_id: analysis.data.id, target_kind: "outfit", target_id: selectedOutfit.combination_id, verdict: "reject" }).then(refresh)
                  }
                >
                  Not my style
                </button>
              </div>
              {(selectedProduct || selectedGarment) && (
                <p className="mt-3 text-[11px] text-muted">
                  {selectedProduct ? `${selectedProduct.title} · ${money(selectedProduct.price_minor, selectedProduct.currency)}` : selectedGarment?.display_name}
                </p>
              )}
            </aside>
          </div>

          <section className="mx-6 mb-10 rounded-[32px] bg-white p-5 lg:mx-8">
            <h2 className="font-display text-[26px] font-semibold tracking-tight">Choose what earns its place.</h2>
            <div className="mt-4 grid gap-6 lg:grid-cols-3">
              {result ? (
                <>
                  <div>
                    <UnlockRanking result={result} />
                    <button onClick={() => setCenterMode("cards")} className="mt-2 text-[12px] font-medium text-pink">
                      Explore the underlying outfits →
                    </button>
                  </div>
                  <BudgetFrontier result={result} />
                  <div>
                    <AlgorithmCompare result={result} />
                    <div className="mt-3 flex items-center justify-between">
                      <div className="flex gap-1">
                        {bag.slice(0, 2).map((item) => (
                          <AuthImage key={item.id} assetId={item.image_asset_id} alt={item.title} className="h-12 w-12 rounded-xl object-cover" />
                        ))}
                      </div>
                      <button onClick={() => setTab("bag")} className="rounded-full bg-pink-soft px-4 py-2 text-xs font-medium text-pink">
                        Compare baskets →
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <p className="col-span-3 text-sm text-muted">
                  Charts use persisted analysis results only. Add 4–10 real candidates, then compute rankings.
                </p>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function OutfitCards({
  looks,
  garments,
  products,
}: {
  looks: Array<Record<string, unknown>>;
  garments: GarmentView[];
  products: ProductView[];
}) {
  const [page, setPage] = useState(0);
  const assets = new Map<string, string | null | undefined>();
  garments.forEach((item) => assets.set(item.id, item.crop_asset_id));
  products.forEach((item) => assets.set(item.id, item.image_asset_id));
  if (!looks.length) {
    return (
      <p className="rounded-[24px] bg-cream px-4 py-10 text-center text-sm text-muted">
        Qualified looks from a persisted analysis appear here.
      </p>
    );
  }
  const pageSize = 2;
  const maxPage = Math.max(0, Math.ceil(looks.length / pageSize) - 1);
  const visible = looks.slice(page * pageSize, page * pageSize + pageSize);
  return (
    <div className="relative">
      <div className="grid gap-3 md:grid-cols-2">
        {visible.map((look, index) => (
          <article key={String(look.combination_id)} className="rounded-[24px] bg-cream p-4">
            <p className="font-display text-xl italic tracking-tight capitalize">
              {String(look.template || `Look ${page * pageSize + index + 1}`).replace(/_/g, " ")}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {(look.garment_ids as string[]).slice(0, 5).map((id) => (
                <AuthImage key={id} assetId={assets.get(id)} alt="" className="h-20 w-[72px] rounded-2xl bg-white object-cover" />
              ))}
            </div>
          </article>
        ))}
      </div>
      {looks.length > pageSize && (
        <>
          <button
            type="button"
            aria-label="Previous looks"
            disabled={page === 0}
            onClick={() => setPage((value) => Math.max(0, value - 1))}
            className="absolute top-1/2 -left-3 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-white text-muted shadow disabled:opacity-30"
          >
            ‹
          </button>
          <button
            type="button"
            aria-label="Next looks"
            disabled={page >= maxPage}
            onClick={() => setPage((value) => Math.min(maxPage, value + 1))}
            className="absolute top-1/2 -right-3 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-white text-muted shadow disabled:opacity-30"
          >
            ›
          </button>
        </>
      )}
    </div>
  );
}

function BagIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M6 8h12l-1 12H7L6 8Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M9 8V7a3 3 0 0 1 6 0v1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function SparkleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 3.2 13.2 8 18 9.2 13.2 10.4 12 15.2 10.8 10.4 6 9.2 10.8 8 12 3.2Z" />
      <path d="M18.5 13.5 19.2 16 21.7 16.7 19.2 17.4 18.5 19.9 17.8 17.4 15.3 16.7 17.8 16 18.5 13.5Z" />
    </svg>
  );
}

function BagGrid({ products, onSelect }: { products: ProductView[]; onSelect: (id: string) => void }) {
  return (
    <div className="rounded-[32px] bg-white p-5">
      <h2 className="font-display text-2xl font-semibold tracking-tight">Shopping bag</h2>
      <p className="text-sm text-muted">Only items you added. No fabricated catalogue.</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        {products.map((item) => (
          <button key={item.id} onClick={() => onSelect(item.id)} className="text-left">
            <AuthImage assetId={item.image_asset_id} alt={item.title} className="h-40 w-full rounded-2xl object-cover" />
            <p className="mt-2 text-sm font-medium">{item.title}</p>
            <p className="text-xs text-muted">
              {money(item.price_minor, item.currency)} · {item.pinned ? "pinned" : item.excluded ? "excluded" : "in bag"}
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}

function PurchaseForm({
  open,
  products,
  onRefresh,
  onError,
  budget,
  setBudget,
  occasion,
  setOccasion,
  footwear,
  setFootwear,
  currency,
  analyzing,
  onAnalyze,
}: {
  open: boolean;
  products: ProductView[];
  onRefresh: () => void;
  onError: (message: string) => void;
  budget: number;
  setBudget: (value: number) => void;
  occasion: string;
  setOccasion: (value: string) => void;
  footwear: boolean;
  setFootwear: (value: boolean) => void;
  currency: string;
  analyzing: boolean;
  onAnalyze: () => void;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({
    title: "",
    price_major: "",
    currency: "USD",
    category: "top",
    colour_family: "",
    pattern_family: "solid",
  });
  const [productFile, setProductFile] = useState<File | null>(null);
  if (!open && products.length) {
    return (
      <div className="rounded-[32px] bg-white p-5">
        <label className="text-sm">Budget {money(budget, currency)}</label>
        <input type="range" min={0} max={50000} step={500} value={budget} onChange={(event) => setBudget(Number(event.target.value))} className="mt-2 w-full accent-pink" />
        <button onClick={onAnalyze} disabled={analyzing} className="mt-4 w-full rounded-full bg-ink py-3 text-sm text-white">
          {analyzing ? "Computing exact basket…" : "Compute rankings"}
        </button>
      </div>
    );
  }
  return (
    <form
      className="space-y-3 rounded-[32px] bg-white p-5"
      onSubmit={async (event) => {
        event.preventDefault();
        if (!productFile) {
          onError("Upload-and-enter-price is the supported production path. Attach the product image.");
          return;
        }
        try {
          await api.createProduct(draft, productFile);
          setDraft({ title: "", price_major: "", currency: draft.currency, category: "top", colour_family: "", pattern_family: "solid" });
          setProductFile(null);
          onRefresh();
        } catch (err) {
          onError(err instanceof Error ? err.message : "Product create failed.");
        }
      }}
    >
      <h3 className="font-display text-lg font-semibold">Add a purchase</h3>
      <input className="w-full rounded-2xl border border-line px-3 py-2" placeholder="Title" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} required />
      <input className="w-full rounded-2xl border border-line px-3 py-2" placeholder="Price" value={draft.price_major} onChange={(event) => setDraft({ ...draft, price_major: event.target.value })} required />
      <select className="w-full rounded-2xl border border-line px-3 py-2" value={draft.category} onChange={(event) => setDraft({ ...draft, category: event.target.value })}>
        <option value="top">Top</option>
        <option value="bottom">Bottom</option>
        <option value="dress">Dress</option>
        <option value="outerwear">Outerwear</option>
        <option value="footwear">Footwear</option>
      </select>
      <input className="w-full rounded-2xl border border-line px-3 py-2" placeholder="Colour family" value={draft.colour_family} onChange={(event) => setDraft({ ...draft, colour_family: event.target.value })} />
      <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setProductFile(event.target.files?.[0] || null)} />
      <button className="w-full rounded-full bg-pink py-3 text-sm text-white">Save candidate</button>
      <p className="text-[11px] text-muted">{products.length} / 10 candidates. Shipping and tax excluded unless supplied.</p>
      <label className="block text-sm">Budget {money(budget, currency)}</label>
      <input type="range" min={0} max={50000} step={500} value={budget} onChange={(event) => setBudget(Number(event.target.value))} className="w-full accent-pink" />
      <select value={occasion} onChange={(event) => setOccasion(event.target.value)} className="w-full rounded-2xl border border-line px-3 py-2 text-sm">
        <option value="any">Any occasion</option>
        <option value="casual">Casual</option>
        <option value="smart_casual">Smart casual</option>
        <option value="office">Office</option>
        <option value="evening">Evening</option>
      </select>
      <label className="flex items-center gap-2 text-xs">
        <input type="checkbox" checked={footwear} onChange={(event) => setFootwear(event.target.checked)} />
        Require footwear
      </label>
      <button type="button" onClick={onAnalyze} disabled={analyzing} className="w-full rounded-full bg-ink py-3 text-sm text-white">
        {analyzing ? "Computing exact basket…" : "Compute rankings"}
      </button>
      <button
        type="button"
        className="text-[11px] text-pink"
        onClick={async () => {
          await api.deleteWorkspace();
          onRefresh();
        }}
      >
        Start over
      </button>
    </form>
  );
}

function Onboarding({ onDone, onError }: { onDone: () => void; onError: (message: string) => void }) {
  return (
    <div className="mx-6 mb-10 rounded-[32px] bg-white px-8 py-16 text-center lg:mx-8">
      <h2 className="font-display text-3xl font-semibold tracking-tight">Start with your own photographs</h2>
      <p className="mx-auto mt-3 max-w-lg text-muted">
        External image processing (Gemini extraction and optional YouCam try-on) needs explicit consent. There is no
        preloaded wardrobe, catalogue, or generated preview.
      </p>
      <button
        onClick={async () => {
          try {
            await api.consent();
            onDone();
          } catch (err) {
            onError(err instanceof Error ? err.message : "Consent failed.");
          }
        }}
        className="mt-6 rounded-full bg-pink px-6 py-3 text-white"
      >
        I consent to external image processing
      </button>
    </div>
  );
}

function HowItWorks() {
  return (
    <div className="mx-6 mb-10 max-w-3xl space-y-4 rounded-[32px] bg-white p-8 lg:mx-8">
      <h2 className="font-display text-3xl font-semibold tracking-tight">How it works</h2>
      <p className="text-muted">
        Closest Chemistry counts rule-qualified outfit options — not guaranteed wear, attractiveness, or physical fit.
        Exact search is exact under declared compatibility rules.
      </p>
      <ol className="list-decimal space-y-2 pl-5 text-sm">
        <li>Upload real outfit photographs and confirm garments before they count.</li>
        <li>Add 4–10 real cart candidates with image, price, and category.</li>
        <li>Compute rankings. Charts use persisted analysis results only.</li>
        <li>Generate live try-on submits a fresh YouCam task when configured; cached results stay labelled.</li>
      </ol>
    </div>
  );
}

function FeedbackPanel({ analysis, onRefresh }: { analysis?: AnalysisView; onRefresh: () => void }) {
  const outfits = analysis?.result?.outfits.filter((item) => item.qualified) || [];
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {outfits.map((outfit) => (
        <div key={String(outfit.combination_id)} className="rounded-[28px] bg-white p-4">
          <p className="text-sm font-medium">Look {String(outfit.combination_id)}</p>
          <p className="text-xs text-muted">{String(outfit.template)}</p>
          <div className="mt-3 flex gap-2">
            <button
              className="rounded-full bg-green px-3 py-1 text-xs text-white"
              onClick={() =>
                api.feedback({ analysis_id: analysis!.id, target_kind: "outfit", target_id: outfit.combination_id, verdict: "approve" }).then(onRefresh)
              }
            >
              Keep this option
            </button>
            <button
              className="rounded-full border border-line px-3 py-1 text-xs"
              onClick={() =>
                api.feedback({ analysis_id: analysis!.id, target_kind: "outfit", target_id: outfit.combination_id, verdict: "reject" }).then(onRefresh)
              }
            >
              Not my style
            </button>
          </div>
        </div>
      ))}
      {!outfits.length && <p className="rounded-[28px] bg-white p-8 text-sm text-muted">Saved looks appear after you approve outfits from a real analysis.</p>}
    </div>
  );
}
