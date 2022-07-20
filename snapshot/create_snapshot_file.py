from pathlib import Path

from snapshot.request_files.snapshot_file import ReqParseError, SnapshotFile
from snapshot.request_files.snapshot_json_file import SnapshotJsonFile
from snapshot.request_files.snapshot_req_file import SnapshotReqFile


def create_snapshot_file(path: str, changeable_macros: list = None) -> SnapshotFile:
    filepath = Path(path)
    if filepath.suffix in (".req", ".snap"):
        return SnapshotReqFile(path, changeable_macros=changeable_macros)
    if filepath.suffix in (".json", ".yaml", ".yml"):
        try:
            return SnapshotJsonFile(filepath, filepath.read_text())
        except OSError as e:
            raise ReqParseError(f'Could not read "{filepath}" load file.', e)
    else:
        raise ReqParseError(
            f"Snapshot file of {filepath.suffix} type is not supported."
        )
