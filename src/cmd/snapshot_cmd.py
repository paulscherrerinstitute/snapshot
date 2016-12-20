import datetime
import logging
import os
import sys
import time

from ..ca_core import PvStatus, ActionStatus, Snapshot, SnapshotError


def save(req_file_path, save_file_path='.', macros=None, force=False, timeout=10):
    if os.path.isdir(save_file_path):
        save_file_path += '/{}_{}.snap'.format(os.path.splitext(os.path.basename(req_file_path))[0],
                                               datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d_%H%M%S'))

    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    logging.info('Start saving the snapshot.')
    if force:
        logging.info('Started in force mode. Unavailable PVs will be ignored.')
    macros = macros or {}
    try:
        snapshot = Snapshot(req_file_path, macros)
    except (IOError, SnapshotError) as e:
        logging.error('Snapshot cannot be loaded due to a following error: {}'.format(e))
        sys.exit(1)

    logging.info('Waiting for PVs connections (timeout: {} s) ...'.format(timeout))
    end_time = time.time() + timeout
    while snapshot.get_disconnected_pvs_names() and time.time() < end_time:
        time.sleep(0.2)

    status, pv_status = snapshot.save_pvs(save_file_path, force)

    if status != ActionStatus.ok:
        for pv_name, status in pv_status.items():
            if status == PvStatus.access_err:
                logging.error('\"{}\": No connection or no read access.'.format(pv_name))
        logging.error('Snapshot file was not saved.')

    else:
        for pv_name, status in pv_status.items():
            if status == PvStatus.access_err:
                logging.warning('\"{}\": Value not saved. No connection or no read access.'.format(pv_name))
        logging.info('Snapshot file was saved.')


def restore(saved_file_path, force=False, timeout=10):
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    logging.info('Start restoring the snapshot.')
    if force:
        logging.info('Started in force mode. Unavailable PVs will be ignored.')

    try:
        # Preparse file to check for any problems in the snapshot file.
        saved_pvs, meta_data, err = Snapshot.parse_from_save_file(saved_file_path)

        if err:
            logging.warning('While loading file following problems were detected:\n * ' + '\n * '.join(err))
        # Use saved file as request file here
        snapshot = Snapshot(saved_file_path, macros=meta_data.get('macros', dict()))

    except (IOError, SnapshotError) as e:
        logging.error('Snapshot cannot be loaded due to a following error: {}'.format(e))
        sys.exit(1)

    logging.info('Waiting for PVs connections (timeout: {} s) ...'.format(timeout))
    end_time = time.time() + timeout

    while snapshot.get_disconnected_pvs_names() and time.time() < end_time:
        time.sleep(0.2)

    # Timeout should be used for complete command. Pass the remaining of the time.
    status, pvs_status = snapshot.restore_pvs_blocking(saved_file_path, force, end_time - time.time())

    if status == ActionStatus.ok:
        for pv_name, pv_status in pvs_status.items():
            if pv_status == PvStatus.access_err:
                logging.warning('\"{}\": Not restored. No connection or no read access.'.format(pv_name))

        logging.info('Snapshot file was restored.')

    elif status == ActionStatus.timeout:
        # In case when no response from some PVs after values were pushed.
        for pv_name, pv_status in pvs_status.items():
            if pv_status == PvStatus.access_err:
                logging.warning('\"{}\": Not restored. No connection or no read access.'.format(pv_name))

        logging.error('Not finished in timeout: {} s. Some PVs may not be restored. Try to increase'
                      ' timeout.'.format(timeout))

    else:
        for pv_name, pv_status in pvs_status.items():
            if pv_status == PvStatus.access_err:
                logging.error('\"{}\": No connection or no read access.'.format(pv_name))

        logging.error('Snapshot file was not restored.')
