"""Asynchronous interactive console.

Modified from Python 3.13.5's `asyncio.__main__` module to provide
an interact() function that uses the current event loop.
"""
import ast
import asyncio
import concurrent.futures
import contextvars
import inspect
import os
import site
import sys
import threading
import types
import warnings

from _colorize import can_colorize, ANSIColors  # type: ignore[import-not-found]
from _pyrepl.console import InteractiveColoredConsole
from _pyrepl.main import CAN_USE_PYREPL

from asyncio import futures


# Global variables that are referenced in the original module
return_code = 0
repl_future = None
keyboard_interrupted = False
console = None
loop = None


class AsyncIOInteractiveConsole(InteractiveColoredConsole):

    def __init__(self, locals, loop):
        super().__init__(locals, filename="<stdin>")
        self.compile.compiler.flags |= ast.PyCF_ALLOW_TOP_LEVEL_AWAIT

        self.loop = loop
        self.context = contextvars.copy_context()

    def runcode(self, code):
        global return_code
        future = concurrent.futures.Future()

        def callback():
            global return_code
            global repl_future
            global keyboard_interrupted

            repl_future = None
            keyboard_interrupted = False

            func = types.FunctionType(code, self.locals)
            try:
                coro = func()
            except SystemExit as se:
                return_code = se.code
                self.loop.stop()
                return
            except KeyboardInterrupt as ex:
                keyboard_interrupted = True
                future.set_exception(ex)
                return
            except BaseException as ex:
                future.set_exception(ex)
                return

            if not inspect.iscoroutine(coro):
                future.set_result(coro)
                return

            try:
                repl_future = self.loop.create_task(coro, context=self.context)
                futures._chain_future(repl_future, future)
            except BaseException as exc:
                future.set_exception(exc)

        loop.call_soon_threadsafe(callback, context=self.context)

        try:
            return future.result()
        except SystemExit as se:
            return_code = se.code
            self.loop.stop()
            return
        except BaseException:
            if keyboard_interrupted:
                self.write("\nKeyboardInterrupt\n")
            else:
                self.showtraceback()
            return self.STATEMENT_FAILED


class REPLThread(threading.Thread):

    def __init__(self, console, locals=None, done_future=None):
        super().__init__(name="Interactive thread", daemon=True)
        self.console = console
        self.locals = locals or {}
        self.done_future = done_future

    def run(self):
        global return_code

        try:
            banner = (
                f'asyncio REPL {sys.version} on {sys.platform}\n'
                f'Use "await" directly instead of "asyncio.run()".\n'
                f'Type "help", "copyright", "credits" or "license" '
                f'for more information.\n'
            )

            self.console.write(banner)

            if startup_path := os.getenv("PYTHONSTARTUP"):
                sys.audit("cpython.run_startup", startup_path)

                import tokenize
                with tokenize.open(startup_path) as f:
                    startup_code = compile(f.read(), startup_path, "exec")
                    exec(startup_code, self.console.locals)

            ps1 = getattr(sys, "ps1", ">>> ")
            if can_colorize() and CAN_USE_PYREPL:
                ps1 = f"{ANSIColors.BOLD_MAGENTA}{ps1}{ANSIColors.RESET}"
            self.console.write(f"{ps1}import asyncio\n")

            if CAN_USE_PYREPL:
                from _pyrepl.simple_interact import (
                    run_multiline_interactive_console,
                )
                try:
                    run_multiline_interactive_console(self.console)
                except SystemExit:
                    # expected via the `exit` and `quit` commands
                    pass
                except BaseException:
                    # unexpected issue
                    self.console.showtraceback()
                    self.console.write("Internal error, ")
                    return_code = 1
            else:
                self.console.interact(banner="", exitmsg="")
        finally:
            warnings.filterwarnings(
                'ignore',
                message=r'^coroutine .* was never awaited$',
                category=RuntimeWarning)

            # Signal that we're done
            if self.done_future and not self.done_future.done():
                loop.call_soon_threadsafe(self.done_future.set_result, return_code)

    def interrupt(self) -> None:
        if not CAN_USE_PYREPL:
            return

        from _pyrepl.simple_interact import _get_reader
        r = _get_reader()
        if r.threading_hook is not None:
            r.threading_hook.add("")  # type: ignore


async def interact(banner=None, locals=None, *, use_pyrepl=None):
    """Run an interactive asyncio REPL using the current event loop.

    Args:
        banner: Optional banner to display at startup
        locals: Optional dictionary of local variables (defaults to calling frame's locals)
        use_pyrepl: Whether to use pyrepl (defaults to auto-detect)

    Returns:
        The return code from the REPL session
    """
    global return_code, loop, console, repl_future, keyboard_interrupted

    # Reset globals
    return_code = 0
    keyboard_interrupted = False
    repl_future = None

    # Get the current event loop
    loop = asyncio.get_running_loop()

    # Determine if we should use pyrepl
    if use_pyrepl is None:
        if os.getenv('PYTHON_BASIC_REPL'):
            use_pyrepl = False
        else:
            use_pyrepl = CAN_USE_PYREPL

    # Set up locals dictionary
    if locals is None:
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            locals = frame.f_back.f_locals.copy()
        else:
            locals = {}

    repl_locals = {'asyncio': asyncio}
    repl_locals.update(locals)

    # Add common builtins if not present
    for key in {'__name__', '__package__', '__loader__', '__spec__', '__builtins__', '__file__'}:
        if key not in repl_locals:
            repl_locals[key] = globals().get(key)

    # Create console
    console = AsyncIOInteractiveConsole(repl_locals, loop)

    # Handle readline setup
    try:
        import readline  # NoQA
    except ImportError:
        readline = None

    interactive_hook = getattr(sys, "__interactivehook__", None)

    if interactive_hook is not None:
        sys.audit("cpython.run_interactivehook", interactive_hook)
        interactive_hook()

    if interactive_hook is site.register_readline:
        # Fix the completer function to use the interactive console locals
        try:
            import rlcompleter
        except:
            pass
        else:
            if readline is not None:
                completer = rlcompleter.Completer(console.locals)
                readline.set_completer(completer.complete)

    # Create a future to track when the REPL is done
    repl_done = asyncio.Future()

    # Create and start the REPL thread
    repl_thread = REPLThread(console, locals, done_future=repl_done)
    repl_thread.start()

    final_return_code = None

    # Wait for the REPL to finish
    try:
        # Use the future to wait for the thread to complete
        final_return_code = await repl_done
    except KeyboardInterrupt:
        keyboard_interrupted = True
        if repl_future and not repl_future.done():
            repl_future.cancel()
        repl_thread.interrupt()
        # If interrupted, wait for the thread to finish gracefully
        if not repl_done.done():
            try:
                final_return_code = await asyncio.wait_for(repl_done, timeout=1.0)
            except asyncio.TimeoutError:
                # Thread didn't finish in time, use current return_code
                final_return_code = return_code
    finally:
        console.write('exiting asyncio REPL...\n')

    return final_return_code


def run_console():
    """Run the asyncio console as a standalone program (original __main__ behavior)."""
    sys.audit("cpython.run_stdin")

    # Create new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _run():
        return await interact()

    try:
        return_code = loop.run_until_complete(_run())
    except KeyboardInterrupt:
        return_code = 0
    finally:
        loop.close()

    sys.exit(return_code)


if __name__ == '__main__':
    run_console()
