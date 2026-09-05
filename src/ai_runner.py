"""Thread-safe helper for the Google GenAI (gemini) client.

The google-genai client is asyncio-native: calling it from a plain worker
thread (the FastAPI background thread that runs the review pipeline) raises
"RuntimeError: There is no current event loop in thread 'Thread-N'".

Every Gemini call site routes through :func:`run_async` (or the convenience
wrappers below), which creates a fresh event loop on the calling thread,
runs the coroutine to completion, and cleans up. This is safe to call from the
main thread, a background thread, or nested calls.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable


def run_async(coro_factory: Callable[[], Any]) -> Any:
    """Run a coroutine (built by ``coro_factory``) to completion on this thread.

    Creates a dedicated event loop so the caller needs no pre-existing loop
    and never inherits one that belongs to another thread.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # Already inside an event loop (e.g. called from async FastAPI code):
        # schedule and await. This keeps the synchronous API usable from async
        # contexts too.
        inner = asyncio.ensure_future(coro_factory())
        return loop.run_until_complete(asyncio.gather(inner))[0]

    new_loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(new_loop)
        return new_loop.run_until_complete(coro_factory())
    finally:
        try:
            new_loop.close()
        finally:
            asyncio.set_event_loop(None)


def call_generate_content(client: Any, model: str, contents: Any) -> Any:
    """Invoke ``client.models.generate_content`` off the main thread safely."""
    return run_async(lambda: _async_generate(client, model, contents))


async def _async_generate(client: Any, model: str, contents: Any) -> Any:
    kwargs = dict(model=model, contents=contents)
    return await client.aio.models.generate_content(**kwargs)


def call_generate_content_sync(client: Any, model: str, contents: Any) -> Any:
    """Blocking variant for code/tests that construct the client directly.

    Builds the response in the calling thread's loop rather than the client's
    own (the sync client is not thread-safe across loops).
    """
    return run_async(lambda: _async_generate(client, model, contents))


def call_embed_content(
    client: Any, model: str, contents: list[str], *, config: Any = None
) -> Any:
    """Invoke ``client.models.embed_content`` off the main thread safely."""
    return run_async(lambda: _async_embed(client, model, contents, config))


async def _async_embed(
    client: Any, model: str, contents: list[str], config: Any = None
) -> Any:
    params: dict[str, Any] = dict(model=model, contents=contents)
    if config is not None:
        params["config"] = config
    return await client.aio.models.embed_content(**params)