"use client";

import { useEffect, useRef } from "react";
import type { Core, EventObject } from "cytoscape";
import type { GarmentView } from "@/lib/api";
import { assetUrl } from "@/lib/api";

type Props = {
  garments: GarmentView[];
  edges: Array<{ source: string; target: string; qualified_outfit_ids: string[] }>;
  selectedId?: string | null;
  onSelect: (id: string) => void;
};

const GROUPS = [
  { id: "top", label: "Your tops", y: 80 },
  { id: "outerwear", label: "Outerwear", y: 250 },
  { id: "dress", label: "Dresses / unlocked looks", y: 250 },
  { id: "bottom", label: "Your bottoms", y: 430 },
  { id: "footwear", label: "Your shoes", y: 430 },
];

export function Constellation({ garments, edges, selectedId, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function mount() {
      const cytoscape = (await import("cytoscape")).default;
      if (cancelled || !host.current) return;
      const byCat: Record<string, GarmentView[]> = {};
      garments.forEach((item) => {
        byCat[item.category] = byCat[item.category] || [];
        byCat[item.category].push(item);
      });
      const nodes = GROUPS.flatMap((group, groupIndex) => {
        const items = byCat[group.id] || [];
        const startX = groupIndex % 2 === 0 ? 140 : 520;
        return [
          {
            data: { id: `label-${group.id}`, label: `${group.label} (${items.length})`, kind: "label" },
            position: { x: startX + items.length * 40, y: group.y - 70 },
            grabbable: false,
          },
          ...items.map((item, index) => ({
            data: {
              id: item.id,
              label: item.display_name,
              kind: item.source_kind === "cart" ? "candidate" : "owned",
              category: item.category,
              image: item.crop_asset_id ? assetUrl(item.crop_asset_id) : "",
            },
            position: { x: startX + index * 92, y: group.y },
          })),
        ];
      });
      const edgeEls = edges.map((edge, index) => ({
        data: {
          id: `e-${index}`,
          source: edge.source,
          target: edge.target,
          outfits: edge.qualified_outfit_ids.length,
        },
      }));
      if (cyRef.current) cyRef.current.destroy();
      const cy = cytoscape({
        container: host.current,
        elements: [...nodes, ...edgeEls],
        layout: { name: "preset" },
        style: [
          {
            selector: "node[kind='label']",
            style: {
              "background-color": "#ffe4f1",
              color: "#111",
              label: "data(label)",
              "font-size": 11,
              "text-valign": "center",
              width: 160,
              height: 28,
              shape: "round-rectangle",
              "border-width": 0,
            },
          },
          {
            selector: "node[kind='owned']",
            style: {
              width: 64,
              height: 64,
              "background-color": "#f6f6f6",
              "border-width": 1,
              "border-color": "#ececec",
              label: "data(label)",
              "font-size": 9,
              "text-valign": "bottom",
              "text-margin-y": 6,
              opacity: 0.72,
              "background-fit": "cover",
              "background-image": "data(image)",
            },
          },
          {
            selector: "node[kind='candidate']",
            style: {
              width: 72,
              height: 72,
              "background-color": "#fff",
              "border-width": 2,
              "border-color": "#245bff",
              label: "data(label)",
              "font-size": 9,
              "text-valign": "bottom",
              "text-margin-y": 6,
              "background-fit": "cover",
              "background-image": "data(image)",
            },
          },
          {
            selector: "edge",
            style: {
              width: 1.5,
              "line-color": "#ff4da0",
              "curve-style": "bezier",
              "target-arrow-shape": "none",
            },
          },
        ],
        userZoomingEnabled: true,
        userPanningEnabled: true,
      });
      cy.on("tap", "node", (event: EventObject) => {
        const id = event.target.id();
        if (!id.startsWith("label-")) onSelect(id);
      });
      cyRef.current = cy;
    }
    mount();
    return () => {
      cancelled = true;
      cyRef.current?.destroy();
    };
  }, [garments, edges, onSelect]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !selectedId) return;
    cy.nodes().forEach((node) => {
      node.style("border-width", node.id() === selectedId ? 3 : node.data("kind") === "candidate" ? 2 : 1);
    });
  }, [selectedId]);

  if (!garments.length) {
    return (
      <div className="flex h-[520px] items-center justify-center text-sm text-muted">
        Upload outfit photographs and confirm garments to draw this constellation. Positions use a category layout, not an embedding.
      </div>
    );
  }

  return (
    <div className="relative">
      <div ref={host} className="h-[560px] w-full bg-white" />
      <p className="absolute bottom-2 left-3 text-[11px] text-muted">
        Compatibility edges are explainable rule matches, not approval. Node placement is a category layout.
      </p>
    </div>
  );
}
