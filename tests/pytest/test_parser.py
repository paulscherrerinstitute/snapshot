import logging
import unittest
import json
import yaml

from snapshot.parser import SnapshotReqFile


logging.basicConfig(level=logging.DEBUG)



class TestSnapshotRead(unittest.TestCase):

    def tearDown(self):
        pass

    def test_req_load(self):
        file_req = '../softioc/test.req'
        # SnapshotReqFile the input req file
        request_file = SnapshotReqFile(file_req)
        # reads return a tuple (pv, metadata)
        pvs = request_file.read()[0]
        metadata = request_file.read()[1]
        metadata_default = {'machine_params':{}}
        # reads each line to a list
        with open(file_req) as f:
            content = f.readlines()
        pvs_content = [x.strip() for x in content] 
        for pv_file, pv_parser in zip(pvs_content, pvs):
            assert pv_file == pv_parser
        assert metadata_default == metadata

    def test_json_load(self):
        file_json = '../pco_cam/pco.json'
        # SnapshotReqFile the input req file
        request_file = SnapshotReqFile(file_json)
        # reads return a tuple (pv, metadata)
        pvs = request_file.read()[0]
        # reads each line to a list
        with open(file_json, 'r') as f:
            data = json.load(f)
        pvs_file = []
        for key, value in data.items():
            for val in value:
                pvs_file.append(str(key)+":"+val)
        assert pvs == pvs_file
    
    def test_yaml_load(self):
        file_yaml = '../pco_cam/pco.yaml'
        # SnapshotReqFile the input req file
        request_file = SnapshotReqFile(file_yaml)
        # reads return a tuple (pv, metadata)
        pvs = request_file.read()[0]
        metadata = request_file.read()[1]
        metadata_default = {'machine_params':{}}
        with open(file_yaml, 'r') as stream:
            try:
                data = yaml.safe_load(stream)[0]
            except yaml.YAMLError as exc:
                print(exc)
        pvs_file = []
        for key, value in data.items():
            for val in value:
                pvs_file.append(str(key)+":"+val)
        assert pvs == pvs_file


