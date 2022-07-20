import datetime
import logging
import os
import re
import sys
import time

from snapshot.ca_core import ActionStatus, PvStatus, Snapshot
from snapshot.core import SnapshotError, get_machine_param_data
from snapshot.parser import parse_from_save_file


def save(
    req_file_path,
    save_file_path=".",
    macros=None,
    force=False,
    timeout=10,
    labels_str=None,
    comment=None,
    filter_param="",
):
    symlink_path = None
    if os.path.isdir(save_file_path):
        symlink_path = save_file_path + "/{}_latest.snap".format(
            os.path.splitext(os.path.basename(req_file_path))[0]
        )
        save_file_path += "/{}_{}.snap".format(
            os.path.splitext(os.path.basename(req_file_path))[0],
            datetime.datetime.fromtimestamp(time.time()).strftime(
                "%Y%m%d_%H%M%S"
            ),
        )

    labels = []
    if labels_str.strip():
        list_labels = labels_str.split(",")
        for label in list_labels:
            label = label.strip()
            label = label.replace(" ", "_")
            if label:
                labels.append(label)

    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(message)s"
    )
    logging.info("Start saving the snapshot.")
    if force:
        logging.info("Started in force mode. Unavailable PVs will be ignored.")
    macros = macros or {}
    try:
        snapshot = Snapshot(req_file_path, macros)
    except (OSError, SnapshotError) as e:
        logging.error(
            f"Snapshot cannot be loaded due to a following error: {e}"
        )
        sys.exit(1)
    logging.info(f"Waiting for PVs connections (timeout: {timeout} s) ...")
    end_time = time.time() + timeout
    while snapshot.get_disconnected_pvs_names() and time.time() < end_time:
        time.sleep(0.2)

    machine_params = snapshot.req_file_metadata.get("machine_params", {})
    params_data = get_machine_param_data(machine_params)
    invalid_params = {
        p: v["value"]
        for p, v in params_data.items()
        if type(v["value"]) not in (float, int, str)
    }
    if invalid_params:
        pv_errors = [
            f"\t{p} ({machine_params[p]}) has no value"
            if v is None
            else f"\t{p} ({machine_params[p]}) has unsupported "
            f"type {type(v)}"
            for p, v in invalid_params.items()
        ]
        if not force:
            logging.error(
                "Machine parameters are not accessible or have "
                "invalid values. Will not proceed without force "
                "mode.\n" + "\n".join(pv_errors)
            )
            return
        logging.info(
            "Machine parameters are not accessible or have "
            "invalid values. Force mode is on, proceeding.\n"
            + "\n".join(pv_errors)
        )
        for p in invalid_params:
            params_data[p] = None

    if filter_param != "":
        list_pvs = snapshot.get_pvs_names()
        srch_filter = re.compile(filter_param)
        remove_pvs = [i for i in list_pvs if srch_filter.fullmatch(i) is None]
        snapshot.remove_pvs(remove_pvs)

    status, pv_status = snapshot.save_pvs(
        save_file_path,
        force=force,
        labels=labels,
        comment=comment,
        machine_params=params_data,
        symlink_path=symlink_path,
    )

    if status != ActionStatus.ok:
        for pv_name, status in pv_status.items():
            if status == PvStatus.access_err:
                logging.error(f'"{pv_name}": No connection or no read access.')
        logging.error("Snapshot file was not saved.")

    else:
        for pv_name, status in pv_status.items():
            if status == PvStatus.access_err:
                logging.warning(
                    f'"{pv_name}": Value not saved. No connection or no read access.'
                )

        logging.info("Snapshot file was saved.")


def restore(saved_file_path, force=False, timeout=10, filter_param=""):
    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(message)s"
    )
    logging.info("Start restoring the snapshot.")
    if force:
        logging.info("Started in force mode. Unavailable PVs will be ignored.")

    try:
        # Preparse file to check for any problems in the snapshot file.
        saved_pvs, meta_data, err = parse_from_save_file(saved_file_path)

        if err:
            logging.warning(
                "While loading file following problems were detected:\n * "
                + "\n * ".join(err)
            )
        # Use saved file as request file here
        snapshot = Snapshot(
            saved_file_path, macros=meta_data.get("macros", dict())
        )

        if filter_param != "":
            list_pvs = snapshot.get_pvs_names()
            srch_filter = re.compile(filter_param)
            remove_pvs = [
                i for i in list_pvs if srch_filter.fullmatch(i) is None
            ]
            snapshot.remove_pvs(remove_pvs)

    except (OSError, SnapshotError) as e:
        logging.error(
            f"Snapshot cannot be loaded due to a following error: {e}"
        )
        sys.exit(1)

    logging.info(f"Waiting for PVs connections (timeout: {timeout} s) ...")
    end_time = time.time() + timeout

    while snapshot.get_disconnected_pvs_names() and time.time() < end_time:
        time.sleep(0.2)

    # Timeout should be used for complete command. Pass the remaining of the
    # time.
    status, pvs_status = snapshot.restore_pvs_blocking(
        saved_file_path, force, end_time - time.time()
    )

    if status == ActionStatus.ok:
        for pv_name, pv_status in pvs_status.items():
            if pv_status == PvStatus.access_err:
                logging.warning(
                    f'"{pv_name}": Not restored. No connection or no write access.'
                )

        logging.info("Snapshot file was restored.")

    elif status == ActionStatus.timeout:
        # In case when no response from some PVs after values were pushed.
        for pv_name, pv_status in pvs_status.items():
            if pv_status == PvStatus.access_err:
                logging.warning(
                    f'"{pv_name}": Not restored. No connection or no write access.'
                )

        logging.error(
            f"Not finished in timeout: {timeout} s. Some PVs may not be restored. Try to increase timeout."
        )

    else:
        for pv_name, pv_status in pvs_status.items():
            if pv_status == PvStatus.access_err:
                logging.error(
                    f'"{pv_name}": No connection or no write access.'
                )

        logging.error("Snapshot file was not restored.")
