from snapshot.ca_core import Snapshot, SnapshotError, SnapshotReqFile

def restore_done(status, forced):
    print('Restore finished [forced mode: {}]'.format(status, forced))
    for pvname, sts in status.items():
        print('{}  -> {}'.format(pvname, sts.name))

macros = {'SYS': 'TST', 'A': 'B'}  # can aslo be macros = "SYS=TST,A=B"
snap = Snapshot('./test.req', macros)

# Save to snap file in force mode and create a symlink
snap.save_pvs('./test_1.snap', force=True, symlink_path='./test_latest.snap')

# None blocking restore from snap file
snap.restore_pvs('./test_1.snap', force=True, callback=restore_done)
# Will not wait for restore to finish.

# Blocking restore. Instead of path we can use dict (same gos for normal restore)
pvs_to_restore = {'TST:B_TST': {'value': 5}}
sts = snap.restore_pvs_blocking(pvs_to_restore)
print('Blocking restore finished with status: ' + sts.name)


# Sometimes user might want to parse req file
req_file = SnapshotReqFile('./test.req', macros=macros)
pvs_list = req_file.read()
print(pvs_list)



