export default function Skeleton({ className = "", rounded = "rounded-md" }) {
  return <div aria-hidden="true" className={`shimmer bg-surface-3 ${rounded} ${className}`} />;
}

export function SkeletonText({ lines = 3, className = "" }) {
  return (
    <div aria-hidden="true" className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={`h-3 ${i === lines - 1 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}

export function LoadingRegion({ label, children, className = "" }) {
  return (
    <div role="status" aria-busy="true" aria-live="polite" className={className}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}
