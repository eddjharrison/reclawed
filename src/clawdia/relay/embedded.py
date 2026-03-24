"""Embedded relay server — start the WebSocket hub in-process as an asyncio task.

This module lets the TUI spin up the relay server without spawning a subprocess,
so the group-chat host and their local Claude instance can share the same event
loop with no extra ports or processes to manage.

Usage::

    server = await start_embedded_relay(port=8765, token="secret")
    # ...later, to clean up:
    server.close()
    await server.wait_closed()
"""

from __future__ import annotations

import asyncio
import functools
import logging

from websockets.asyncio.server import serve

from clawdia.relay.server import _handler

logger = logging.getLogger(__name__)


async def start_embedded_relay(
    port: int = 8765,
    host: str = "0.0.0.0",
    token: str | None = None,
) -> asyncio.Server:
    """Start the relay WebSocket server as a non-blocking background task.

    Returns the ``asyncio.Server`` handle.  The server runs in the background
    on the current event loop.  Call ``server.close()`` followed by
    ``await server.wait_closed()`` to shut it down gracefully.

    The server accepts connections on *all* interfaces by default (``0.0.0.0``)
    so that remote participants can reach it.  Callers should share the
    machine's public/LAN IP with the connection string instead of ``0.0.0.0``.

    Parameters
    ----------
    port:
        TCP port to listen on (default: 8765).
    host:
        Interface to bind (default: "0.0.0.0").
    token:
        Optional shared token; if set, connecting clients must supply it as
        the ``?token=`` query parameter.
    """
    handler = functools.partial(_handler, shared_token=token)

    # ``serve()`` from websockets returns an async context manager; we enter it
    # here and deliberately *do not* exit so the server stays alive.  We get
    # back the underlying asyncio.Server object which the caller can use to
    # shut down later.
    ws_server = await serve(handler, host, port)
    logger.info("Embedded relay listening on ws://%s:%d", host, port)
    return ws_server
