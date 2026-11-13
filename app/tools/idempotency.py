import hashlib


def action_key(plan_version: int, action_type: str, resource: str, intended_time: str) -> str:
    # Retries of the same planned action share a key; a new plan version gets a new key.
    raw = f'{plan_version}|{action_type}|{resource}|{intended_time}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()
