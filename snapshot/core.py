from epics import PV, ca
import numpy
from enum import Enum
import json
import logging
from time import monotonic, sleep, time
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor


_start_time = time()
_print_trace = False


def since_start(message=None):
    seconds = '{:.2f}'.format(time() - _start_time)
    if message and _print_trace:
        print(message, "at", seconds, 's.')
    else:
        return seconds


def enable_tracing(enable=True):
    global _print_trace
    _print_trace = enable


# A shared thread pool that can be used from anywhere for tasks that
# should run in background, but not indefinitely.
global_thread_pool = ThreadPoolExecutor(16)


class _BackgroundWorkers:
    """
    A simple interface to suspend, resume and register background threads for
    tasks that run for the lifetime of the program, e.g. updating of PV values.
    These tasks should be suspended when they are not needed and when their CPU
    usage would needlessly prolong execution of other functions. Examples are
    saving and restoring PVs, and reading a request file.
    """

    def __init__(self):
        self._workers = []
        self._count = 0

    def suspend(self):
        if self._count == 0:
            for w in self._workers:
                w.suspend()
        self._count += 1

    def resume(self):
        if self._count > 0:
            self._count -= 1
            if self._count == 0:
                for w in self._workers:
                    w.resume()

    def register(self, worker):
        if worker not in self._workers:
            self._workers.append(worker)

    def unregister(self, worker):
        idx = self._workers.index(worker)
        del self._workers[idx]


background_workers = _BackgroundWorkers()


# Exceptions
class SnapshotError(Exception):
    """
    Parent exception class of all snapshot exceptions.
    """
    pass

class _bytesSnap(bytes):
    """
    Because of bug in pyepics, ca.put() doesn't work when a single element is put to waveform of stings.
    Bug is due to a ca.put() function uses len(value) to determine weather it is an array or a single value, but
    len(bytes) gives you a number of characters len(b'abc') --> 3.
    To work properly with pyepics len should return 1 indicating there is only one element.
    """

    def __len__(self):
        return 1

class PvStatus(Enum):
    """
    Returned by SnapshotPv on save_pv() and restore_pv() methods. Possible states:
        access_err: Not connected or not read/write permission at the time of action.
        ok: Action succeeded.
        no_value: Returned if value (save_pv) or desired value (restore_pv) for action is not defined.
        equal: Returned if restore value is equal to current PV value (no need to restore).
        type_err: Returned if type of restore value is wrong
    """
    access_err = 0
    ok = 1
    no_value = 2
    equal = 3
    type_err = 4

# Subclass PV to be to later add info if needed
class SnapshotPv(PV):
    """
    Extended PV class with non-blocking methods to save and restore pvs. It
    does not enable monitors, instead relying on values from PvUpdater. Without
    PvUpdater, it will always perform a get().

    Note: PvUpdater is a "friend class" and uses this class' internals.
    """

    def __init__(self, pvname, connection_callback=None, **kw):
        self.conn_callbacks = dict()  # dict {idx: callback}
        if connection_callback:
            self.add_conn_callback(connection_callback)
        self.is_array = False

        # Internals for synchronization with PvUpdater
        self._last_value = None
        self._initialized = False
        self._pvget_lock = Lock()
        self._pvget_completer = None

        super().__init__(pvname,
                         connection_callback=self._internal_cnct_callback,
                         auto_monitor=False,
                         connection_timeout=None, **kw)

    @PV.value.getter
    def value(self):
        """
        Overriden PV.value property. Since auto_monitor is disabled, this
        property would perform a get(). Instead, we return the last value
        that was fetched by PvUpdater, emulating auto_monitor using periodic
        updates. If no value was fetched yet, do a get().
        """
        value = self._last_value  # it could be updated in the background
        if not self._initialized:
            self._initialized = True
            value = self.get(use_monitor=False, with_ctrlvars=True)
            self._last_value = value
        return value

    def get(self, *args, **kwargs):
        """
        Overriden PV.get() function. If not arguments are given, returns the
        cached value, otherwise calls PV.get(). See also SnapshotPv.value().
        """

        if args or kwargs:
            # Because PvUpdater uses low-level ca calls that can time
            # out, get() must be able to handle incomplete gets that
            # it didn't start itself.
            with self._pvget_lock:
                if self._pvget_completer is not None:
                    val = self._pvget_completer()
                    if val is None:
                        # There is never an infinite timeout. If this call
                        # timed out as well, we still can't proceed.
                        return None
                return PV.get(self, *args, **kwargs)

        return self.value

    def save_pv(self):
        """
        Non blocking CA get. Does not block if there is no connection or no read access. Returns latest value
        (monitored) or None if not able to get value. It also returns status of the action (see PvStatus)

        :return: (value, status)

            value: PV value.

            status: Status of save action as PvStatus type.
        """
        if self.connected:
            # Must be after connection test. If checking access when not
            # connected pyepics tries to reconnect which takes some time.
            if self.read_access:
                saved_value = self.get(use_monitor=False)
                if self.is_array:
                    if numpy.size(saved_value) == 0:
                        # Empty array is equal to "None" scalar value
                        saved_value = None
                    elif numpy.size(saved_value) == 1:
                        # make scalars as arrays
                        saved_value = numpy.asarray([saved_value])

                if saved_value is None:
                    logging.debug('No value returned for channel ' + self.pvname)
                    return saved_value, PvStatus.no_value
                else:
                    return saved_value, PvStatus.ok
            else:
                return None, PvStatus.access_err
        else:
            return None, PvStatus.access_err

    def restore_pv(self, value, callback=None):
        """
        Executes asynchronous CA put if value is different to current PV value. Success status of this action is
        returned in callback.

        :param value: Value to be put to PV.
        :param callback: callback function in which success of restoring is monitored

        :return:
        """
        if self.connected:
            # Must be after connection test. If checking access when not
            # connected pyepics tries to reconnect which takes some time.
            if self.write_access:
                if value is None:
                    callback(pvname=self.pvname, status=PvStatus.no_value)

                elif not self.compare_to_curr(value):
                    if isinstance(value, str):
                        # pyepics needs value as bytes not as string
                        value = str.encode(value)

                    elif self.is_array and len(value) and isinstance(value[0], str):
                        # Waveform of strings. Bytes expected to be put.
                        n_value = list()
                        for item in value:
                            n_value.append(item.encode())

                        if len(n_value) == 1:
                            # Special case to overcome the pypeics bug. Use _bytesSnap instead of bytes, since
                            # len(_bytesSnap('abcd')) is always 1.
                            value = _bytesSnap(n_value[0])
                        else:
                            value = n_value

                    try:
                        self.put(value, wait=False, callback=callback, callback_data={"status": PvStatus.ok})

                    except TypeError as e:
                        callback(pvname=self.pvname, status=PvStatus.type_err)

                elif callback:
                    # No need to be restored.
                    callback(pvname=self.pvname, status=PvStatus.equal)

            elif callback:
                callback(pvname=self.pvname, status=PvStatus.access_err)

        elif callback:
            callback(pvname=self.pvname, status=PvStatus.access_err)

    @staticmethod
    def value_to_str(value: str, is_array: bool):
        """
        Get snapshot style string representation of provided value.

        :param value: Value to be represented as string.
        :param is_array: Should be treated as an array.

        :return: String representation of value
        """
        if is_array:
            if numpy.size(value) == 0:
                # Empty array is equal to "None" scalar value
                return None
            elif numpy.size(value) == 1:
                # make scalars as arrays
                return json.dumps(numpy.asarray([value]).tolist())

            elif not isinstance(value, list):
                return json.dumps(value.tolist())

            else:
                # Is list of strings. This is returned by pyepics when using waveform of string
                return json.dumps(value)

        elif isinstance(value, str):
            # visualize without ""
            return value
        else:
            return json.dumps(value)

    def compare_to_curr(self, value):
        """
        Compare value to current PV value.

        :param value: Value to be compared.

        :return: Result of comparison.
        """
        return SnapshotPv.compare(value, self.value, self.is_array)

    @staticmethod
    def compare(value1, value2, is_array=False):
        """
        Compare two values snapshot style (handling numpy arrays) for waveforms.

        :param value1: Value to be compared to value2.
        :param value2: Value to be compared to value1.
        :param is_array: Are values to be compared arrays?

        :return: Result of comparison.
        """

        if is_array:
            # Because of how pyepics works, array value can also be sent as scalar (nord=1) and
            # numpy.size() will return 1
            # or as (type: epics.dbr.c_double_Array_0) if array is empty --> numpy.size() will
            # return 0

            if value1 is not None and not isinstance(value1, numpy.ndarray) and numpy.size(value1) == 1:
                value1 = numpy.array([value1])
            elif numpy.size(value1) == 0:
                value1 = None

            if value2 is not None and not isinstance(value2, numpy.ndarray) and numpy.size(value2) == 1:
                value2 = numpy.array([value2])
            elif numpy.size(value2) == 0:
                value2 = None

            return numpy.array_equal(value1, value2)

        else:
            return value1 == value2

    def add_conn_callback(self, callback):
        """
        Set connection callback.

        :param callback:
        :return: Connection callback index
        """
        if self.conn_callbacks:
            idx = 1 + max(self.conn_callbacks.keys())
        else:
            idx = 0

        self.conn_callbacks[idx] = callback
        return idx

    def clear_callbacks(self):
        """
        Removes all user callbacks and connection callbacks.

        :return:
        """
        self.conn_callbacks = {}
        super().clear_callbacks()

    def remove_conn_callback(self, idx):
        """
        Remove connection callback.
        :param idx: callback index
        :return:
        """
        if idx in self.conn_callbacks:
            self.conn_callbacks.pop(idx)

    def _internal_cnct_callback(self, conn, **kw):
        """
        Snapshot specific handling of connection status on pyepics connection_callback. Check if PV is array, then call
        user callback if provided.

        :param conn: True if connected, False if not connected.
        :param kw:

        :return:
        """

        # PV layer of pyepics handles arrays strange. In case of having a waveform with NORD field "1" it will not
        # interpret it as array. Instead of native "pv.count" which is a NORD field of waveform record it should use
        # number of may elements "pv.nelm" (NELM field). However this also acts wrong because it simply does following:
        # if count == 1, then nelm = 1
        # The true NELM info can be found with ca.element_count(self.chid).
        self.is_array = (ca.element_count(self.chid) > 1)

        # If user specifies his own connection callback, call it here.
        for clb in self.conn_callbacks.values():
            clb(conn=conn, **kw)

    @staticmethod
    def macros_substitution(txt: str, macros: dict):
        """
        Returns string txt with substituted macros (defined as {macro: value}).

        :param txt: String with macros.
        :param macros: Dictionary with {macro: value} pairs.

        :return: txt with replaced macros.
        """
        for key in macros:
            macro = "$(" + key + ")"
            txt = txt.replace(macro, macros[key])
        return txt


class PvUpdater:
    """
    Manages a thread that periodically updated PV values. The values are both
    cached in the PV objects (see SnapshotPv.value()) and passed to a callback.
    A normal python thread is used instead of a CAThread because a fresh CA
    context is needed.
    """
    updateRate = 1.  # seconds
    _sleep_quantum = 0.1

    def __init__(self, callback=lambda: None, **kwargs):
        self._callback = callback
        self._lock = Lock()
        self._pvs = []
        self._quit = False
        self._suspend = False
        self._thread = Thread(target=self._run)
        background_workers.register(self)

    def __del__(self):
        background_workers.unregister(self)
        self.stop()

    def start(self):
        self._thread.start()

    def stop(self):
        self._quit = True
        if self._thread.is_alive():
            self._thread.join()

    def suspend(self):
        with self._lock:
            self._suspend = True

    def resume(self):
        with self._lock:
            self._suspend = False

    def set_pvs(self, pvs):
        with self._lock:
            self._pvs = list(pvs)

    @staticmethod
    def _get_start(pv):
        try:
            if pv.connected:
                ca.get_with_metadata(pv.chid, wait=False, as_numpy=True)
                # To be used by SnapshotPv.get() in case we time out.
                pv._pvget_completer = \
                    lambda: PvUpdater._get_complete(pv, wait=True)
        except ca.ChannelAccessException:
            pass

    @staticmethod
    def _get_complete(pv, wait=False):
        try:
            if pv.connected:
                timeout = PvUpdater.updateRate if wait is False else None
                md = ca.get_complete_with_metadata(pv.chid, as_numpy=True,
                                                   timeout=timeout)
                if md is None:
                    return None
                pv._pvget_completer = None
                pv._last_value = md['value']
                return md['value']
            else:
                return None
        except ca.ChannelAccessException:
            return None

    def _run(self):
        ca.use_initial_context()
        startTime = monotonic()
        while not self._quit:
            while monotonic() < startTime + self.updateRate:
                sleep(self._sleep_quantum)
                if self._quit:
                    return

            startTime = monotonic()
            with self._lock:
                if self._suspend:  # this check needs the lock
                    continue

                since_start("Started getting PV values")

                report_init_timeout = False
                report = "Some connected PVs are timing out while " \
                    "fetching ctrlvars, causing slowdowns."
                for pv in self._pvs:
                    pv._pvget_lock.acquire()
                    if not pv._initialized:
                        # Units and precision will be needed in the GUI. Fetch
                        # them now and cache them, so that GUI won't need to.
                        if pv.connected:
                            ctrl = pv.get_ctrlvars()
                            # It can timeout, so don't rely on it.
                            if ctrl:
                                pv._initialized = True
                            else:
                                if not report_init_timeout:
                                    retport_init_timeout = True
                                    logging.debug(report)
                    # get_ctrlvars() does not fetch the value, so we still need
                    # to do it. It is safe to do even in the case of timeout
                    # because the ctrl and value requests are orthogonal in
                    # pyepics. There is a very slim chance that pv._last_value
                    # remains none even if it when pv._initialized is True
                    # if the value get times out, but that's no different from
                    # what pyepics itself does. <rant>pyepics is quite bad at
                    # handling timeouts</rant>.
                    self._get_start(pv)

                vals = [self._get_complete(pv) for pv in self._pvs]

                for pv in self._pvs:
                    pv._pvget_lock.release()

                since_start("Finished getting PV values")

            self._callback(vals)
