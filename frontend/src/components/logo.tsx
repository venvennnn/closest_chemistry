export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-pink text-white">
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M8 4h8l3 7-7 10L5 11l3-7z" />
        </svg>
      </span>
      {!compact && <span className="text-lg font-semibold tracking-tight">Closest Chemistry</span>}
    </div>
  );
}
