import logging
from enum import Enum
import concurrent.futures
from threading import Lock, Thread
from time import monotonic, sleep, time

import numpy
from epics import PV, ca, caput

_start_time = time()
_print_trace = False


def since_start(message=None):
    seconds = '{:.2f}'.format(time() - _start_time)
    if message and _print_trace:
        print(seconds, message)
    else:
        return seconds


def enable_tracing(enable=True):
    global _print_trace
    _print_trace = enable


def process_record(pvname):
    """Assuming 'pvname' is part of an EPICS record, write to its PROC field."""
    record = pvname.split('.')[0]
    caput(f'{record}.PROC', 1)


class _BackgroundWorkers:
    """
    A simple interface to suspend, resume and register background threads for
    tasks that run for the lifetime of the program, e.g. updating of PV values.
    These tasks should be suspended when they are not needed and when their CPU
    usage would needlessly prolong execution of other functions. Examples are
    saving and restoring PVs, and reading a request file.

    A task is registered by name. This name can be used to selectively suspend
    and resume a particular task.
    """

    def __init__(self):
        self._workers = {}
        self._explicitly_suspended = {}
        self._count = 0

    def is_suspended(self):
        return self._count > 0

    def suspend_one(self, worker_name):
        if not self._explicitly_suspended[worker_name]:
            self._explicitly_suspended[worker_name] = True
            if not self.is_suspended():
                self._workers[worker_name].suspend()

    def resume_one(self, worker_name):
        if self._explicitly_suspended[worker_name]:
            self._explicitly_suspended[worker_name] = False
            if not self.is_suspended():
                self._workers[worker_name].resume()

    def suspend(self):
        if self._count == 0:
            since_start("Pausing background threads")
            for n, w in self._workers.items():
                if not self._explicitly_suspended[n]:
                    w.suspend()
            since_start("Background threads suspended")
        self._count += 1

    def resume(self):
        if self._count > 0:
            self._count -= 1
            if self._count == 0:
                since_start("Resuming background threads")
                for n, w in self._workers.items():
                    if not self._explicitly_suspended[n]:
                        w.resume()

    def register(self, worker_name, worker):
        assert(worker_name not in self._workers)
        self._workers[worker_name] = worker
        self._explicitly_suspended[worker_name] = False

    def unregister(self, worker_name):
        if worker_name in self._workers:
            del self._workers[worker_name]
            del self._explicitly_suspended[worker_name]


background_workers = _BackgroundWorkers()


class BackgroundThread:
    """
    A base class for a background thread. Automatically registers with
    background_workers. Override the _run() method. The new method must check
    the _lock, _quit and _suspend variables and act appropriately. The
    _periodic_loop() method does this for you and is handy for writing periodic
    tasks.
    """

    __sleep_quantum = 0.1

    def __init__(self, name=None, **kwargs):
        assert(name is not None)
        self._name = name
        self._lock = Lock()
        self._quit = False
        self._suspend = False
        self._thread = Thread(target=self._run)

    def __del__(self):
        if self._thread.is_alive():
            self.stop()

    def start(self):
        background_workers.register(self._name, self)
        self._thread.start()

    def stop(self):
        background_workers.unregister(self._name)
        self._quit = True
        if self._thread.is_alive():
            self._thread.join()

    def suspend(self):
        with self._lock:
            self._suspend = True

    def resume(self):
        with self._lock:
            self._suspend = False

    def _run(self):
        raise NotImplementedError(
            "The BackgroundThread class should not be used directly.")

    def _periodic_loop(self, period, task):
        """
        If you wish to implement a simple periodic task, call this function
        from _run(). It handles quitting and suspending. It will execute task()
        every period seconds. _lock is held while task() executes; task() may
        release it, but must take it again before returning.
        """

        startTime = monotonic()
        while not self._quit:
            while monotonic() < startTime + period:
                sleep(self.__sleep_quantum)
                if self._quit:
                    return

            startTime = monotonic()
            with self._lock:
                if not self._suspend:  # this check needs the lock
                    task()


def get_machine_param_data(machine_params):
    """For each machine parameter (given in dict {name: pv_name}), get PV
    data as dict. The data includes 'value', 'units', 'precision'. Returns a
    dict of {name: data}. In case of error, all values in data are None."""

    background_workers.suspend()
    pvs = [PV(name, auto_monitor=False, connection_timeout=None)
           for name in machine_params.values()]
    results = [p.get_with_metadata(form='ctrl', as_numpy=True) for p in pvs]
    background_workers.resume()

    return {p: {key: (v.get(key) if v is not None else None)
                for key in ('value', 'units', 'precision')}
            for p, v in zip(machine_params.keys(), results)}


# Exceptions
class SnapshotError(Exception):
    """
    Parent exception class of all snapshot exceptions.
    """
    pass


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

    def __init__(self, pvname, user_config=None, connection_callback=None, **kw):
        # dict format {idx: callback}
        if user_config is None:
            user_config = {}
        self.conn_callbacks = {}
        if connection_callback:
            self.add_conn_callback(connection_callback)
        self.is_array = False

        # Internals for synchronization with PvUpdater
        self._last_value = None
        self._initialized = False
        self._pvget_lock = Lock()
        self._pvget_completer = None
        self._user_config = user_config

        super().__init__(pvname,
                         connection_callback=self._internal_cnct_callback,
                         auto_monitor=False,
                         connection_timeout=None, **kw)

    @property
    def initialized(self):
        return self._initialized

    @PV.value.getter
    def value(self):
        """
        Overriden PV.value property. Since auto_monitor is disabled, this
        property would perform a get(). Instead, we return the last value
        that was fetched by PvUpdater, emulating auto_monitor using periodic
        updates. If no value was fetched yet, return None, but don't block.

        This method is never used when we _really_ want a value. In such cases,
        use get().
        """
        return self._last_value if self._initialized else None

    def get(self, *args, **kwargs):
        """
        Overriden PV.get() function. If no arguments are given and the value
        was initialized by PvUpdater, returns the cached value, otherwise calls
        PV.get(). It also makes one-element arrays behave consistently: unless
        it is given 'as_numpy=False', it will always return an ndarray.

        See also SnapshotPv.value().
        """

        if args or kwargs or not self._initialized:
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

                val = PV.get(self, *args, **kwargs)

                # pyepics is inconsistent with regard to one-element arrays;
                # see _internal_cnct_callback() for explanation. Moreover, it
                # will return string arrays as lists. To keep everything
                # uniform, we convert all lists to ndarrays.
                if val is not None and self.is_array:
                    if numpy.size(val) == 0:
                        val = None
                    elif (numpy.size(val) == 1 and
                          kwargs.get('as_numpy', True) and
                          not isinstance(val, numpy.ndarray)):
                        val = numpy.asarray([val])
                    elif (kwargs.get('as_numpy', True) and
                          not isinstance(val, numpy.ndarray)):
                        val = numpy.asarray(val)

                return val

        return self.value

    @PV.precision.getter
    def precision(self):
        """Override so as to not block until PvUpdater initializes ctrlvars."""
        prec = self._user_config.get('precision', -1)
        if prec >= 0:
            return prec
        return self._args.get('precision', None)

    @PV.units.getter
    def units(self):
        """Override to not block until PvUpdater initializes ctrlvars."""
        return self._args.get('units', None)

    @PV.enum_strs.getter
    def enum_strs(self):
        return self._args.get('enum_strs', None)

    def save_pv(self):
        """
        Non-blocking CA get. Does not block if there is no connection or no read access. Returns the latest value
        (monitored) or None if not able to get value. It also returns status of the action (see PvStatus)

        :return: (value, status)

            value: PV value.

            status: Status of save action as PvStatus type.
        """
        if self.connected and self.read_access:
            saved_value = self.get(use_monitor=False)
            if saved_value is None:
                logging.debug(f'No value returned for channel {self.pvname}')
                return saved_value, PvStatus.no_value
            else:
                return saved_value, PvStatus.ok
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
                    try:
                        self.put(
                            value,
                            wait=False,
                            callback=callback,
                            callback_data={
                                "status": PvStatus.ok})

                    except TypeError:
                        callback(pvname=self.pvname,
                                 status=PvStatus.type_err)

                elif callback:
                    # No need to be restored.
                    callback(pvname=self.pvname, status=PvStatus.equal)

            elif callback:
                callback(pvname=self.pvname, status=PvStatus.access_err)

        elif callback:
            callback(pvname=self.pvname, status=PvStatus.access_err)

    @staticmethod
    def value_to_display_str(value, precision):
        """
        Get snapshot style string representation of provided value. For display
        purposes only!

        :param value: Value to be represented as string.
        :param precision: display precision for floats

        :return: String representation of value
        """

        # First, check for the most common stuff
        if value is None:
            return ''
        elif isinstance(value, float):
            # return PrintFloat(value, precision)

            # old behavior was causing error with float
            # and precision zero. now a float
            #  with precision 0 is shown as integer
            try:
                fmt = f'{{:.{precision}f}}' if precision >= 0 else '{:f}'
            except TypeError as e:
                fmt = '{:f}'
            return fmt.format(value)

        elif isinstance(value, str):
            return value
        elif isinstance(value, numpy.ndarray):
            if value.dtype.kind == 'f':
                fmt = f'{{:.{precision}f}}' if precision and precision > 0 else '{:f}'
            else:
                fmt = '{}'

            if numpy.size(value) > 3:
                # abbreviate long arrays
                return f'[{fmt} ... {fmt}]'.format(value[0], value[-1])
            else:
                return '[' + ' '.join(fmt.format(x) for x in value) + ']'
        else:  # integer values come here
            return f'{value:.0f}'
            # return str(value)

    def compare_to_curr(self, value):
        """
        Compare value to current PV value with zero tolerance.

        :param value: Value to be compared.

        :return: Result of comparison.
        """
        return SnapshotPv.compare(value, self.value, 0.)

    @staticmethod
    def compare(value1, value2, tolerance):
        """
        Compare two values snapshot style (handling numpy arrays) for waveforms.

        :param value1: Value to be compared to value2.
        :param value2: Value to be compared to value1.
        :param tolerance: Comparison is done as |v1 - v2| <= tolerance

        :return: Result of comparison.
        """

        if value1 is None or value2 is None:
            return value1 is value2

        if isinstance(value1, float) and isinstance(value2, float):
            return abs(value1 - value2) <= tolerance
        elif any(isinstance(x, numpy.ndarray) for x in (value1, value2)):
            try:
                return numpy.allclose(value1, value2, atol=tolerance, rtol=0)
            except (TypeError, ValueError):
                # Array of non-numeric types or with unequal lengths
                return numpy.array_equal(value1, value2)
        else:
            return value1 == value2

    def add_conn_callback(self, callback):
        """
        Set connection callback.

        :param callback:
        :return: Connection callback index
        """
        idx = 1 + max(self.conn_callbacks.keys()) if self.conn_callbacks else 0
        self.conn_callbacks[idx] = callback
        return idx

    def clear_callbacks(self, **kwargs):
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
            macro = f"$({key})"
            txt = txt.replace(macro, macros[key])
        return txt


class PvUpdater(BackgroundThread):
    """
    Manages a thread that periodically updated PV values. The values are both
    cached in the PV objects (see SnapshotPv.value()) and passed to a callback.
    A normal python thread is used instead of a CAThread because a fresh CA
    context is needed.
    """
    timeout = 1.0

    def __init__(self, callback=lambda: None, **kwargs):
        super().__init__(name='pv_updater', **kwargs)
        self._callback = callback
        self._pvs = []
        self._update_rate = 5.0  # seconds

    def set_update_rate(self, new_update_rate):
        self._update_rate = float(new_update_rate)

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
    def _process_pv(pv):
        initialized = False
        report_init_timeout = False
        pv._pvget_lock.acquire()
        if not pv._initialized and pv.connected:
            ctrl = pv.get_ctrlvars()
            # It can timeout, so don't rely on it.
            if ctrl:
                # Defer setting init status until we are ready to
                # release the lock.
                initialized = True
            else:
                report_init_timeout = True
            PvUpdater._get_start(pv)

        val = PvUpdater._get_complete(pv)

        pv._initialized |= initialized
        pv._pvget_lock.release()
        return val, report_init_timeout

    @staticmethod
    def _get_complete(pv, wait=False):
        try:
            if not pv.connected or not pv._pvget_completer:
                return None
            timeout = PvUpdater.timeout if wait is False else None
            md = ca.get_complete_with_metadata(pv.chid, as_numpy=True,
                                               timeout=timeout)
            if md is None:
                return None
            pv._pvget_completer = None
            val = md['value']

            # Handle arrays. See comment in SnapshotPv.get()
            if val is not None and pv.is_array:
                if numpy.size(val) == 0:
                    val = None
                elif (numpy.size(val) == 1 and
                      not isinstance(val, numpy.ndarray)):
                    val = numpy.asarray([val])
                elif not(isinstance(val, numpy.ndarray)):
                    val = numpy.asarray(val)

            pv._last_value = val
            return val

        except (ca.ChannelAccessException, ca.ChannelAccessGetFailure):
            # The GetFailure exception happens on pyepics 3.4 if PVs reconnect
            # between _get_start() and _get_complete(). Which is good: older
            # versions just kept silently returning None and wouldn't reconnect
            # properly.
            pv._pvget_completer = None
            pv._last_value = None
            return None

    def _run(self):
        ca.use_initial_context()
        self._periodic_loop(self._update_rate, self._task)

    def _task(self):
        since_start("Started getting PV values")

        report = "Some connected PVs are timing out while " \
            "fetching ctrlvars, causing slowdowns."

        with concurrent.futures.ThreadPoolExecutor() as executor:
            values_and_timeouts = executor.map(PvUpdater._process_pv, self._pvs)

        vals = list(map(lambda x: x[0], values_and_timeouts))
        if any(map(lambda x: x[1], values_and_timeouts)):
            logging.debug(report)

        since_start("Finished getting PV values")

        self._lock.release()
        try:
            self._callback(vals)
        finally:
            self._lock.acquire()
