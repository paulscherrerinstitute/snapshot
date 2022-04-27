from snapshot.ca_core import ActionStatus, Snapshot
from snapshot.request_files.snapshot_req_file import SnapshotReqFile


def restore_done(status, forced):
    print('Restore finished [forced mode: {}]'.format(status, forced))
    for pvname, sts in status.items():
        print('{}  -> {}'.format(pvname, sts.name))


macros = {'SYS': 'TST', 'A': 'B'}  # can aslo be macros = "SYS=TST,A=B"
snap = Snapshot('./test.req', macros)


print("------- Saving to file -------")

# Save to snap file in force mode and create a symlink
sts, pvs_sts = snap.save_pvs(
    './test_1.snap', force=True, symlink_path='./test_latest.snap')
print('Save finished with status: ' + sts.name)
for pvname, pv_sts in pvs_sts.items():
    print('{}  -> {}'.format(pvname, pv_sts.name))


print("------- Non-blocking restore -------")


# Non-blocking restore from snap file
sts, pvs_sts = snap.restore_pvs(
    './test_1.snap', force=True, callback=restore_done)
# Will not wait for restore to finish. If restore started successfully, then pvs_sts
# is returned in callback.
print('Restore started with status {}'.format(sts))
if sts == ActionStatus.no_conn:
    # Since we are in force mode, this case will not happen and is there only for demonstration.
    for pvname, pv_sts in pvs_sts.items():
        print('{}  -> {}'.format(pvname, pv_sts.name))

print("------- Blocking restore -------")

# Blocking restore. Instead of path we can use dict (same gos for normal restore)
pvs_to_restore = {'TST:B_TST': {'value': 5}}
sts, pvs_sts = snap.restore_pvs_blocking(pvs_to_restore)
print('Blocking restore finished with status: ' + sts.name)
for pvname, pv_sts in pvs_sts.items():
    print('{}  -> {}'.format(pvname, pv_sts.name))


print("------- Parsing request file -------")

# Sometimes user might want to parse req file
req_file = SnapshotReqFile('./test.req', macros=macros)
pvs_list = req_file.read()
print(pvs_list)
