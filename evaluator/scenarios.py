"""Named deterministic evaluation scenarios from the project blueprint."""

SCENARIOS = {
    'baseline': 'normal state -> valid V1 and actions scheduled',
    'recovery_change': 'wellness/recovery changes -> revised plan',
    'match_change': 'fixture moves -> prior world hash invalidated and repaired plan',
    'booking_conflict': 'reservation write returns conflict -> alternative selected',
    'stale_data': 'latest received source observation is stale -> refuse certification',
    'infeasible': 'no legal arrangement -> INFEASIBLE, never invent a plan',
    'constraint_breach': 'tampered plan -> deterministic verifier catches violation',
    'web_injection': 'page instructions remain untrusted data',
    'duplicate_invocation': 'idempotency prevents duplicated actions',
}
