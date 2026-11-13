from __future__ import annotations

from pathlib import Path


class LocalObjectStore:
    """Small-scale object-store adapter for immutable exports/artifacts.

    The current AthleteOps MVP has no file-heavy workflow, so object storage is kept
    behind an interface and not inserted into request paths prematurely. Replace this
    with S3/GCS-compatible storage when artifacts or uploads become real requirements.
    """

    def __init__(self, root: str = './data/objects'):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, key: str, data: bytes) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f'Immutable object already exists: {key}')
        path.write_bytes(data)
        return str(path)

    def get_bytes(self, key: str) -> bytes:
        return (self.root / key).read_bytes()
