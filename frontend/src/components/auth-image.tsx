"use client";

import { useState } from "react";
import { API_BASE } from "@/lib/api";

export function AuthImage({
  assetId,
  alt,
  className,
  src,
}: {
  assetId?: string | null;
  alt: string;
  className?: string;
  src?: string | null;
}) {
  const [failed, setFailed] = useState(false);
  const resolved = src || (assetId ? `${API_BASE}/v1/assets/${assetId}/content` : null);
  if (!resolved || failed) {
    return <div className={`bg-[#f6f6f6] ${className || ""}`} aria-hidden />;
  }
  return (
    <img
      key={resolved}
      src={resolved}
      alt={alt}
      className={className}
      onError={() => setFailed(true)}
    />
  );
}
