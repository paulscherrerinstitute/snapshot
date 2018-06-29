import unittest
import logging

logging.basicConfig(level=logging.DEBUG)

from snapshot.ca_core.snapshot_ca import Snapshot


class TestSnapshotReqFile(unittest.TestCase):

    def tearDown(self):
        pass

    def test_load(self):
        snapshot = Snapshot("testfiles/SF_settings.req")
        # request_file = SnapshotReqFile("testfiles/SF_timing.req")
        # pvs = request_file.read()

        print()
        # print(pvs)
        # print(len(pvs))
        print(snapshot.get_disconnected_pvs_names())
        print("# disconnected: %d" % len(snapshot.get_disconnected_pvs_names()))
        print("# connected: %d" % (len(snapshot.pvs) - len(snapshot.get_disconnected_pvs_names())))
        print()

        snapshot.clear_pvs()
        # logging.info(len(pvs))
