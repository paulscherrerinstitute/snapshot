import logging
import json

import pytest
import yaml

from snapshot.snapshot_files import create_snapshot_file
from tests.pytest.helper_functions import base_dir

logging.basicConfig(level=logging.DEBUG)

default_metadata = {'machine_params': {}}


def build_pv_list(data: dict) -> list:
    pvs = list()
    for key, values in data.items():
        pvs += [f"{key}:{val}" for val in values]
    return pvs


def test_req_load():
    file_req = base_dir() / 'softioc' / 'test.req'
    file_content = file_req.read_text().splitlines()
    # SnapshotReqFile the input req file
    request_file = create_snapshot_file(str(file_req))
    # reads return a tuple (pv, metadata)
    pvs, metadata, pvs_config = request_file.read()

    assert file_content == pvs
    assert default_metadata == metadata


@pytest.mark.skip(reason="filters and metadata break test for now")
def test_json_load():
    file_json = base_dir() / 'pco_cam' / 'pco.json'
    # SnapshotReqFile the input req file
    request_file = create_snapshot_file(str(file_json))
    # reads return a tuple (pv, metadata)
    pvs, metadata = request_file.read()
    # reads each line to a list
    data = json.loads(file_json.read_text())
    pvs_from_file = build_pv_list(data)

    assert pvs_from_file == pvs
    assert default_metadata == metadata


@pytest.mark.skip(reason="Seems not implemented yet?")
def test_yaml_load():
    file_yaml = base_dir() / 'pco_cam' / 'pco.yaml'
    # SnapshotReqFile the input req file
    request_file = create_snapshot_file(str(file_yaml))
    # reads return a tuple (pv, metadata)
    pvs, metadata = request_file.read()

    data = yaml.safe_load(file_yaml.read_text())[0]
    pvs_from_file = build_pv_list(data)

    assert pvs_from_file == pvs
    assert default_metadata == metadata
