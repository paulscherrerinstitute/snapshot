from pathlib import Path

from snapshot.core import SnapshotError
from snapshot.request_files.snapshot_req_file import SnapshotReqFile
from snapshot.request_files.snapshot_json_file import SnapshotJsonFile
from snapshot.request_files.snapshot_file import SnapshotFile


def create_snapshot_file(path: str, changeable_macros: list = None) -> SnapshotFile:
    filepath = Path(path)
    if filepath.suffix == '.req':
        return SnapshotReqFile(path, changeable_macros=changeable_macros)
    if filepath.suffix in ('.json', '.yaml', '.yml'):
        return SnapshotJsonFile(path, changeable_macros=changeable_macros)
    else:
        raise SnapshotError(f'Snapshot file of {filepath.suffix} type is not supported.')
