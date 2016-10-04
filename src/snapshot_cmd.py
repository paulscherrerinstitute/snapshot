import time
import datetime
import logging
import os
from .snapshot_ca import PvStatus, ActionStatus, Snapshot, macros_substitution, parse_macros, parse_dict_macros_to_text, stop_snapshot_app
import epics


def save(req_file_path, save_file_path='.', macros=None, force=False, timeout=10):
    req_file_name = os.path.basename(req_file_path)

    if os.path.isdir(save_file_path):
        save_file_path += '/{}_{}.snap'.format(os.path.splitext(req_file_name)[0],
                                              datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d_%H%M%S'))

    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    logging.info('Start saving the snapshot.')
    if force:
        logging.info('Started in force mode. Unavailable PVs will be ignored.')
    macros = macros or {}
    snapshot = Snapshot(req_file_path, macros)

    logging.info('Waiting for PVs connections (timeout: {} s) ...'.format(timeout))
    end_time = time.time() + timeout
    while not snapshot.all_connected and time.time() < end_time:
        time.sleep(0.2)

    status, pv_status = snapshot.save_pvs(req_file_name, save_file_path, force)

    if status != ActionStatus.ok:
        for pv_name in snapshot.get_not_connected_pvs_names():
            logging.error('\"{}\" cannot be accessed.'.format(pv_name))
        logging.info('Snapshot file was not saved.')
    else:
        for pv_name, status in pv_status.items():
            if status == PvStatus.access_err:
                logging.info('\"{}\": Not saved. No connection or no read access.'.format(pv_name))
        logging.info('Snapshot file was saved.')

    stop_snapshot_app() # shutdown CA


def restore(saved_file_path, force=False, timeout=10):
    snapshot = Snapshot(saved_file_path) # Use saved file as request file here

    # Prparse file to check for any problems in the snapshot file.
    saved_pvs, meta_data, err = snapshot.parse_from_save_file(saved_file_path)

    if err:
        logging.warning('While loading file following problems were detected:\n * ' + '\n * '.join(err))

    end_time = time.time() + timeout
    while not snapshot.all_connected and time.time() < end_time:
        time.sleep(0.2)

    # Timeout should be used for complete command. Pass the remaining of the time.
    status = snapshot.restore_pvs_blocking(saved_file_path, force, end_time - time.time())
    if status == ActionStatus.ok:
        for pv_name in snapshot.get_not_connected_pvs_names():
            logging.info('\"{}\": Not restored. No connection or no read access.'.format(pv_name))
        logging.info('Snapshot file was restored.')

    elif status == ActionStatus.timeout:
        # In case when no response from some PVs after values were pushed.
        # Currently no mechanism to determine which did not respond
        logging.error('Not finished in timeout: {} s. Some PVs may not be restored. Try to increase'
                      ' timeout.'.format(timeout))

    else:
        for pv_name in snapshot.get_not_connected_pvs_names():
            logging.error('\"{}\" cannot be accessed.'.format(pv_name))
        logging.info('Snapshot file was not restored.')

    stop_snapshot_app() # shutdown CA