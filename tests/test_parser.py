import logging
import unittest

from snapshot.parser import SnapshotReqFile

logging.basicConfig(level=logging.DEBUG)


class TestSnapshotReqFile(unittest.TestCase):

    def tearDown(self):
        pass

    def test_load(self):
        request_file = SnapshotReqFile("testfiles/SF_settings.req")
        # request_file = SnapshotReqFile("testfiles/SF_timing.req")
        pvs = request_file.read()

        pv_dict = {pv: 1 for pv in pvs}
        print()
        print(pvs)
        print(len(pvs))
        print(len(pv_dict))
        print(pv_dict)
        print()

        logging.info(len(pvs))
