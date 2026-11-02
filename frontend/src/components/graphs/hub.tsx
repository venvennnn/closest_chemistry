"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { AnalysisResult, GarmentView, ProductView } from "@/lib/api";
import { AuthImage } from "@/components/auth-image";

type HubItem = { id: string; name: string; asset?: string | null; owned: boolean };

export function CombinationHub({
  garments,
  products,
  result,
  selectedId,
  onSelect,
  onSeeOutfits,
}: {
  garments: GarmentView[];
  products: ProductView[];
  result?: AnalysisResult | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onSeeOutfits?: () => void;
}) {
  const byId = useMemo(() => {
    const map = new Map<string, HubItem>();
    garments.forEach((item) =>
      map.set(item.id, {
        id: item.id,
        name: item.display_name || item.category,
        asset: item.crop_asset_id,
        owned: item.source_kind !== "cart",
      }),
    );
    products.forEach((item) =>
      map.set(item.id, { id: item.id, name: item.title, asset: item.image_asset_id, owned: false }),
    );
    return map;
  }, [garments, products]);

  const selected = selectedId
    ? byId.get(selectedId)
    : products[0]
      ? byId.get(products[0].id)
      : garments[0]
        ? byId.get(garments[0].id)
        : null;
  const hubId = selected?.id;

  const analysisNeighbors = useMemo(() => {
    if (!hubId) return [] as HubItem[];
    const neighborIds = new Set<string>();
    (result?.edges || []).forEach((edge) => {
      if (edge.source === hubId) neighborIds.add(edge.target);
      if (edge.target === hubId) neighborIds.add(edge.source);
    });
    return [...neighborIds].map((id) => byId.get(id)).filter(Boolean) as HubItem[];
  }, [byId, hubId, result?.edges]);

  const neighbors = useMemo(() => {
    if (analysisNeighbors.length) return analysisNeighbors.slice(0, 6);
    return [...byId.values()].filter((item) => item.id !== hubId).slice(0, 4);
  }, [analysisNeighbors, byId, hubId]);

  const left = neighbors.filter((_, index) => index % 2 === 0);
  const right = neighbors.filter((_, index) => index % 2 === 1);
  const fromAnalysis = analysisNeighbors.length > 0;

  const wrapRef = useRef<HTMLDivElement>(null);
  const hubRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef(new Map<string, HTMLButtonElement>());
  const [paths, setPaths] = useState<string[]>([]);
  const [scale, setScale] = useState(1);

  useLayoutEffect(() => {
    function measure() {
      const wrap = wrapRef.current;
      const hub = hubRef.current;
      if (!wrap || !hub) return;
      const wr = wrap.getBoundingClientRect();
      const hr = hub.getBoundingClientRect();
      const hx = hr.left + hr.width / 2 - wr.left;
      const hy = hr.top + hr.height / 2 - wr.top;
      const next: string[] = [];
      neighbors.forEach((item) => {
        const el = nodeRefs.current.get(item.id);
        if (!el) return;
        const r = el.getBoundingClientRect();
        const x = r.left + r.width / 2 - wr.left;
        const y = r.top + r.height / 2 - wr.top;
        const toward = hx - x;
        const c1x = x + toward * 0.35;
        const c2x = hx - toward * 0.18;
        next.push(`M ${x} ${y} C ${c1x} ${y}, ${c2x} ${hy}, ${hx} ${hy}`);
      });
      setPaths(next);
    }
    measure();
    const frame = requestAnimationFrame(measure);
    const ro = new ResizeObserver(measure);
    if (wrapRef.current) ro.observe(wrapRef.current);
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [neighbors, hubId, scale]);

  if (!selected) {
    return (
      <div className="flex h-72 items-center justify-center rounded-[28px] bg-cream/60 text-sm text-muted">
        Add closet photos and a purchase to see what connects. Placement is a layout, not an embedding.
      </div>
    );
  }

  return (
    <div className="relative">
      <div
        ref={wrapRef}
        className="relative flex min-h-[300px] items-center justify-center gap-10 overflow-hidden py-6"
        style={{ transform: `scale(${scale})`, transformOrigin: "center" }}
      >
        <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
          {paths.map((d, index) => (
            <path
              key={`${d}-${index}`}
              d={d}
              fill="none"
              stroke="#ff2d8b"
              strokeWidth="2.2"
              strokeLinecap="round"
              opacity="0.85"
            />
          ))}
        </svg>
        <div className="relative z-10 flex flex-col gap-5">
          {left.map((item) => (
            <HubNode
              key={item.id}
              item={item}
              onSelect={onSelect}
              register={(el) => {
                if (el) nodeRefs.current.set(item.id, el);
                else nodeRefs.current.delete(item.id);
              }}
            />
          ))}
        </div>
        <div
          ref={hubRef}
          className="relative z-10 w-44 rounded-[28px] border-[2.5px] border-pink bg-white p-3 text-center shadow-[0_0_0_6px_rgba(255,45,139,0.08),0_16px_40px_rgba(255,45,139,0.12)]"
        >
          <AuthImage assetId={selected.asset} alt={selected.name} className="mx-auto h-28 w-24 rounded-2xl object-cover" />
          <p className="mt-2 text-sm font-semibold">{selected.name}</p>
          <p className="text-[11px] text-muted">
            {selected.owned ? "Owned" : "Explore combinations with your closet."}
          </p>
          <button type="button" onClick={onSeeOutfits} className="mt-1 text-[11px] font-medium text-pink">
            See outfits →
          </button>
        </div>
        <div className="relative z-10 flex flex-col gap-5">
          {right.map((item) => (
            <HubNode
              key={item.id}
              item={item}
              onSelect={onSelect}
              register={(el) => {
                if (el) nodeRefs.current.set(item.id, el);
                else nodeRefs.current.delete(item.id);
              }}
            />
          ))}
        </div>
      </div>
      {!fromAnalysis && neighbors.length > 0 && (
        <p className="text-center text-[11px] text-muted">
          These placements are a layout. Rule-matched connections appear after a persisted analysis.
        </p>
      )}
      <div className="absolute bottom-1 right-1 flex gap-1">
        <button
          type="button"
          aria-label="Zoom out"
          onClick={() => setScale((value) => Math.max(0.8, Number((value - 0.1).toFixed(1))))}
          className="flex h-7 w-7 items-center justify-center rounded-full border border-line bg-white text-sm text-muted"
        >
          −
        </button>
        <button
          type="button"
          aria-label="Zoom in"
          onClick={() => setScale((value) => Math.min(1.3, Number((value + 0.1).toFixed(1))))}
          className="flex h-7 w-7 items-center justify-center rounded-full border border-line bg-white text-sm text-muted"
        >
          +
        </button>
      </div>
    </div>
  );
}

function HubNode({
  item,
  onSelect,
  register,
}: {
  item: HubItem;
  onSelect: (id: string) => void;
  register: (el: HTMLButtonElement | null) => void;
}) {
  return (
    <button
      ref={register}
      type="button"
      onClick={() => onSelect(item.id)}
      className="w-[104px] rounded-2xl bg-white p-2 text-left shadow-[0_8px_24px_rgba(40,20,20,0.06)]"
    >
      <AuthImage assetId={item.asset} alt={item.name} className="h-[72px] w-full rounded-xl object-cover" />
      <p className="mt-1 truncate text-[11px] font-medium">{item.name}</p>
      <p className="text-[10px] text-muted">{item.owned ? "Owned" : "Considering"}</p>
    </button>
  );
}
