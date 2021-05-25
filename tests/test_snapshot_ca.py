import logging
import unittest

from snapshot.ca_core.snapshot_ca import Snapshot

logging.basicConfig(level=logging.DEBUG)


class TestSnapshotReqFile(unittest.TestCase):

    def tearDown(self):
        pass

    def test_load(self):
        snapshot = Snapshot("testfiles/SF_settings.req")
        # request_file = SnapshotReqFile("testfiles/SF_timing.req")
        # pvs = request_file.read()

        print()
        # print(pvs)

        print(snapshot.get_disconnected_pvs_names())
        print("# disconnected: %d" %
              len(snapshot.get_disconnected_pvs_names()))
        print("# connected: %d" % (len(snapshot.pvs) -
              len(snapshot.get_disconnected_pvs_names())))
        print(len(snapshot.pvs))
        print()

        snapshot.clear_pvs()
        # logging.info(len(pvs))
