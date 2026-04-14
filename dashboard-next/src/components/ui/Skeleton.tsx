'use client';

interface SkeletonProps {
  className?: string;
  variant?: 'text' | 'circular' | 'rectangular' | 'card';
  width?: string | number;
  height?: string | number;
  lines?: number;
}

function SkeletonBase({ className = '', width, height }: { className?: string; width?: string | number; height?: string | number }) {
  return (
    <div
      className={`animate-pulse rounded-lg bg-[var(--border-color)] ${className}`}
      style={{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height,
      }}
    />
  );
}

export default function Skeleton({ className = '', variant = 'text', width, height, lines = 1 }: SkeletonProps) {
  if (variant === 'card') {
    return (
      <div className={`bg-[var(--surface)] border border-[var(--border-color)] rounded-2xl p-5 space-y-3 ${className}`}>
        <div className="flex items-center justify-between">
          <SkeletonBase className="h-10 w-10 rounded-xl" />
          <SkeletonBase className="h-4 w-16" />
        </div>
        <SkeletonBase className="h-7 w-20" />
        <SkeletonBase className="h-3 w-28" />
      </div>
    );
  }

  if (variant === 'circular') {
    return (
      <SkeletonBase
        className={`rounded-full ${className}`}
        width={width || 40}
        height={height || 40}
      />
    );
  }

  if (variant === 'rectangular') {
    return (
      <SkeletonBase
        className={className}
        width={width || '100%'}
        height={height || 120}
      />
    );
  }

  // text variant: supports multiple lines
  if (lines > 1) {
    return (
      <div className={`space-y-2 ${className}`}>
        {Array.from({ length: lines }).map((_, i) => (
          <SkeletonBase
            key={i}
            className="h-4"
            width={i === lines - 1 ? '70%' : '100%'}
          />
        ))}
      </div>
    );
  }

  return (
    <SkeletonBase
      className={`h-4 ${className}`}
      width={width || '100%'}
      height={height}
    />
  );
}

export function SkeletonRow() {
  return (
    <div className="flex items-center gap-4 px-5 py-4">
      <SkeletonBase className="w-3 h-3 rounded-full" />
      <div className="flex-1 space-y-1.5">
        <SkeletonBase className="h-4 w-48" />
        <SkeletonBase className="h-3 w-72" />
      </div>
      <SkeletonBase className="h-5 w-16 rounded-full" />
      <SkeletonBase className="h-5 w-14 rounded-full" />
      <SkeletonBase className="h-3 w-12" />
    </div>
  );
}
