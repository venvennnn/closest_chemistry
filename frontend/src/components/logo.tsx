export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className="relative inline-block h-7 w-10" aria-hidden>
        <span className="absolute left-0 top-0.5 h-6 w-6 rounded-full border-[2.5px] border-pink" />
        <span className="absolute left-3.5 top-0.5 h-6 w-6 rounded-full border-[2.5px] border-pink" />
      </span>
      {!compact && (
        <span className="text-[22px] font-semibold tracking-tight text-ink">
          Closest Chemistry
        </span>
      )}
    </div>
  );
}
