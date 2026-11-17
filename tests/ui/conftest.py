"""Shared helpers for the GUI tests."""

import gc
import os
import sys
import tempfile
import tkinter

import pytest


def _pin_tcl_std_channels():
    """Give Tcl standard channels that pytest's capture cannot close (Windows).

    Tcl builds its stdin/stdout/stderr channels once per thread, from the
    handles GetStdHandle() returns at that moment, and keeps them. pytest's
    default fd-level capture swaps fds 0-2 with os.dup2 around every test,
    and on Windows the CRT's dup2 *closes* the OS handle the fd held before
    and re-points the process std handles at the new one. Tcl is then left
    holding closed handle values, which Windows recycles for the next file
    anybody opens - typically Tcl's own init.tcl/tk.tcl while the next Tk()
    starts up. The symptoms were intermittent and varied: "couldn't read file
    .../init.tcl: No error", "invalid command name tcl_findLibrary", or a Tcl
    panic killing the interpreter; a GUI test either errored or, when it hit
    display_available() at collection time, silently skipped.

    The fix is to let Tcl see private handles that nothing else ever closes
    while it creates those channels, and to keep that first interpreter (and
    so the channels) alive for the session; the process std handles are put
    back immediately. One sink per stream: Tcl refuses three standard
    channels on one handle, and NUL is a character device it would treat as
    a console. POSIX has no equivalent problem - dup2 does not invalidate
    anything Tcl holds there.
    """
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
    kernel32.SetStdHandle.restype = wintypes.BOOL
    # STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE ((DWORD)-10/-11/-12)
    streams = (0xFFFFFFF6, 0xFFFFFFF5, 0xFFFFFFF4)
    sinks = {n: tempfile.TemporaryFile(buffering=0) for n in streams}
    saved = {n: kernel32.GetStdHandle(n) for n in streams}
    for n in streams:
        kernel32.SetStdHandle(n, msvcrt.get_osfhandle(sinks[n].fileno()))
    try:
        interp = tkinter.Tcl()
        # create all three channels now, while the private handles are current
        interp.eval("fconfigure stdin; fconfigure stdout; fconfigure stderr")
    finally:
        for n, handle in saved.items():
            kernel32.SetStdHandle(n, handle)
    return interp, sinks


# Must run before the first Tcl interpreter of the session, i.e. at import of
# this conftest - before any test module under tests/ui is collected.
_TCL_STD_CHANNELS = _pin_tcl_std_channels() if sys.platform == "win32" else None


def display_available() -> bool:
    """Whether a real Tk root window can be created here.

    Only an X11/Wayland desktop announces itself through the environment; a
    headless Linux runner (no Xvfb) has neither variable, and the check spares
    it a Tk() that can only fail. Windows and macOS have no such variable at
    all - their windowing system is simply there in a desktop session - so on
    those platforms only creating the root decides. Gating them on $DISPLAY
    silently skipped every display test on Windows.
    """
    if sys.platform not in ("win32", "darwin") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        return False
    try:
        tkinter.Tk().destroy()
        return True
    except tkinter.TclError:
        return False


@pytest.fixture(autouse=True)
def _finalise_tk_garbage_on_the_main_thread():
    """Collect each GUI test's Tk garbage here, on the main thread (#89).

    A destroyed window's widgets form reference cycles, so its tkinter
    ``Variable``s and ``Image``s are freed by the cyclic GC - in whichever
    thread happens to trigger the next collection. Their ``__del__`` calls into
    Tcl; from a thread other than the interpreter's, tkinter hands the call to
    the interpreter thread and waits up to about a second for that thread to
    be in ``mainloop()``, then raises "main thread is not in main loop". A
    destroyed root's interpreter never is again, so every such object costs a
    second. A later test that runs ``MainWindow``'s background run thread made
    that thread inherit a hundred-odd of them: it sat in planning for over a
    minute (test_run_cancel on Linux CI). Worse, freeing the last reference to
    an interpreter off its thread aborts the process (Tcl_AsyncDelete).

    The app itself is not exposed: it has one root, alive and in mainloop()
    for the whole run, so those calls are simply marshalled to the GUI thread.
    """
    yield
    gc.collect()
