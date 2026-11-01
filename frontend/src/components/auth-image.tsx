"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function AuthImage({
  assetId,
  token,
  alt,
  className,
}: {
  assetId?: string | null;
  token: string;
  alt: string;
  className?: string;
}) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!assetId) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    fetch(`${API}/v1/assets/${assetId}/content`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => (response.ok ? response.blob() : Promise.reject()))
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (!cancelled) setSrc(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setSrc(null);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [assetId, token]);

  if (!assetId || !src) {
    return <div className={`bg-[#f6f6f6] ${className || ""}`} aria-hidden />;
  }
  return <img src={src} alt={alt} className={className} />;
}
