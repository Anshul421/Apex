import type { PropsWithChildren, ReactNode } from 'react';

export function Panel({ title, subtitle, action, children, className = '' }: PropsWithChildren<{ title?: string; subtitle?: string; action?: ReactNode; className?: string }>) {
  return (
    <section className={`panel ${className}`}>
      {(title || subtitle || action) && (
        <div className="panel-header">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {action && <div className="panel-action">{action}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Metric({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {hint && <div className="metric-hint">{hint}</div>}
    </div>
  );
}

export function EmptyState({ title, children }: PropsWithChildren<{ title: string }>) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <span>{children}</span>
    </div>
  );
}
