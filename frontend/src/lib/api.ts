const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API}${path}`, { ...init, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed (${response.status})`);
  }
  return payload as T;
}

export const api = {
  workspace: (token: string) => request<WorkspaceView>("/v1/workspace", token),
  consent: (token: string) =>
    request("/v1/consents", token, {
      method: "POST",
      body: JSON.stringify({
        granted: true,
        kind: "external_image_processing",
        policy_version: "2026-11-01",
      }),
    }),
  upload: async (token: string, kind: string, file: File) => {
    const body = new FormData();
    body.append("kind", kind);
    body.append("file", file);
    return request<{ id: string }>("/v1/assets", token, { method: "POST", body });
  },
  extract: (token: string, assetId: string) =>
    request<{ job_id: string }>("/v1/assets/" + assetId + "/extract", token, { method: "POST" }),
  job: (token: string, jobId: string) => request<JobView>(`/v1/jobs/${jobId}`, token),
  garments: (token: string) => request<{ items: GarmentView[] }>("/v1/garments", token),
  patchGarment: (token: string, id: string, body: Record<string, unknown>) =>
    request(`/v1/garments/${id}`, token, { method: "PATCH", body: JSON.stringify(body) }),
  merge: (token: string, targetId: string, sourceIds: string[]) =>
    request("/v1/garments/merge", token, {
      method: "POST",
      body: JSON.stringify({ target_id: targetId, source_ids: sourceIds, confirmed: true }),
    }),
  products: (token: string) => request<{ items: ProductView[] }>("/v1/products", token),
  ingestUrl: (token: string, body: Record<string, unknown>) =>
    request("/v1/products/url", token, { method: "POST", body: JSON.stringify(body) }),
  createProduct: async (token: string, fields: Record<string, string>, file: File) => {
    const body = new FormData();
    Object.entries(fields).forEach(([key, value]) => body.append(key, value));
    body.append("file", file);
    return request("/v1/products", token, { method: "POST", body });
  },
  patchCart: (token: string, id: string, body: Record<string, unknown>) =>
    request(`/v1/cart/${id}`, token, { method: "PATCH", body: JSON.stringify(body) }),
  createAnalysis: (token: string, body: Record<string, unknown>) =>
    request<{ analysis_id: string; job_id: string }>("/v1/analyses", token, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  analysis: (token: string, id: string) => request<AnalysisView>(`/v1/analyses/${id}`, token),
  outfit: (token: string, analysisId: string, combinationId: string) =>
    request(`/v1/analyses/${analysisId}/outfits/${combinationId}`, token),
  feedback: (token: string, body: Record<string, unknown>) =>
    request("/v1/feedback", token, { method: "POST", body: JSON.stringify(body) }),
  feedbackSummary: (token: string) => request<FeedbackSummary>("/v1/feedback/summary", token),
  tryon: (token: string, body: Record<string, unknown>) =>
    request<{ tryon_id: string; job_id: string }>("/v1/tryon", token, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  tryonStatus: (token: string, id: string) => request<TryOnView>(`/v1/tryon/${id}`, token),
  deleteWorkspace: (token: string) => request("/v1/workspace", token, { method: "DELETE" }),
};

export function assetUrl(id: string) {
  return `${API}/v1/assets/${id}/content`;
}

export type WorkspaceView = {
  workspace_id: string;
  currency: string;
  consent: { id: string; policy_version: string; granted_at: string } | null;
  onboarding_required: boolean;
  counts: Record<string, number>;
  has_tryon_photo: boolean;
  latest_analysis_id: string | null;
  latest_analysis_status: string | null;
};

export type JobView = {
  id: string;
  kind: string;
  status: string;
  error_safe: string | null;
  result: Record<string, unknown> | null;
};

export type GarmentView = {
  id: string;
  display_name: string;
  category: string;
  subtype?: string | null;
  colour?: string | null;
  colour_family?: string | null;
  pattern?: string | null;
  pattern_family?: string | null;
  formality_min?: number | null;
  formality_max?: number | null;
  status: string;
  needs_review: boolean;
  analysis_eligible: boolean;
  youcam_eligible: boolean;
  source_kind: string;
  crop_asset_id?: string | null;
};

export type ProductView = {
  id: string;
  title: string;
  price_minor: number;
  currency: string;
  category: string;
  image_asset_id: string;
  metadata_origin: string;
  shipping_tax_included: boolean;
  pinned: boolean;
  excluded: boolean;
  cart_item_id: string | null;
};

export type AnalysisView = {
  id: string;
  status: string;
  budget_minor: number;
  currency: string;
  occasion: string;
  footwear_required: boolean;
  error_safe: string | null;
  result: AnalysisResult | null;
};

export type AnalysisResult = {
  wardrobe_cluster_count: number;
  rejected_infeasible: string | null;
  disclaimer: string;
  clusters: Array<Record<string, unknown>>;
  outfits: Array<Record<string, unknown>>;
  edges: Array<{ source: string; target: string; qualified_outfit_ids: string[]; evidence: unknown[] }>;
  standalone: Array<Record<string, unknown>>;
  exact: Record<string, unknown>;
  greedy_marginal: Record<string, unknown>;
  cheapest_first: Record<string, unknown>;
  standalone_yield: Record<string, unknown>;
  frontier: Array<Record<string, unknown>>;
  synergy: Array<Record<string, unknown>>;
  comparison: Array<Record<string, unknown>>;
};

export type FeedbackSummary = { approved: number; rejected: number; denominator: number; note: string };
export type TryOnView = {
  id: string;
  status: string;
  live: boolean;
  cache_hit: boolean;
  result_asset_id: string | null;
  limitation: string | null;
  error_safe: string | null;
  label: string;
};
