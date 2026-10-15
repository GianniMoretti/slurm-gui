"""Runs an asyncio event loop in a background thread and hands results back to the Qt thread.

All network I/O (asyncssh) lives on that loop, so the GUI never blocks. Callbacks passed to
:meth:`AsyncBridge.submit` always run on the Qt main thread.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from PyQt6.QtCore import QObject, pyqtSignal

T = TypeVar("T")


class AsyncBridge(QObject):
    _deliver = pyqtSignal(object, object)   # (callback, argument), emitted from the loop thread

    def __init__(self) -> None:
        super().__init__()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="asyncio", daemon=True)
        self._thread.start()
        self._deliver.connect(lambda fn, arg: fn(arg))

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    def submit(
        self,
        coro: Awaitable[T],
        done: Callable[[T], None] | None = None,
        error: Callable[[BaseException], None] | None = None,
    ) -> concurrent.futures.Future[T]:
        """Schedule ``coro`` on the loop; ``done``/``error`` are called on the Qt thread."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def finished(f: concurrent.futures.Future[T]) -> None:
            if f.cancelled():
                return
            exc = f.exception()
            if exc is not None:
                if error is not None:
                    self._deliver.emit(error, exc)
            elif done is not None:
                self._deliver.emit(done, f.result())

        future.add_done_callback(finished)
        return future

    async def ask_main(self, fn: Callable[[Callable[[Any], None]], None]) -> Any:
        """From loop code: call ``fn(reply)`` on the Qt thread and wait until the UI calls ``reply(value)``.

        The UI can answer whenever it likes (e.g. after the user fills an inline form), so no modal
        dialog is needed. Only the first reply counts.
        """
        answer: asyncio.Future[Any] = self._loop.create_future()

        def reply(value: Any) -> None:
            self._loop.call_soon_threadsafe(lambda: answer.done() or answer.set_result(value))

        self._deliver.emit(lambda _arg: fn(reply), None)
        return await answer

    def shutdown(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)
