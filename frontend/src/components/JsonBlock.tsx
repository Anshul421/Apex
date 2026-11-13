export function JsonBlock({ value, compact = false }: { value: unknown; compact?: boolean }) {
  return (
    <pre className={compact ? 'json-block compact' : 'json-block'}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
