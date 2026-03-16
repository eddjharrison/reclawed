"""Persistent Claude session using the Agent SDK.

Replaces the subprocess-per-prompt ``ClaudeProcess`` with a long-lived
``ClaudeSDKClient`` that maintains real conversation context across
multiple queries within a session.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

from reclawed.claude import StreamError, StreamEvent, StreamResult, StreamSessionId, StreamToken

log = logging.getLogger(__name__)

# Default tools the SDK client is allowed to use.
DEFAULT_TOOLS = ["Read", "Edit", "Bash", "Glob", "Grep", "Write"]


class ClaudeSession:
    """Persistent wrapper around ``ClaudeSDKClient``.

    Unlike ``ClaudeProcess`` (one subprocess per prompt), this maintains a
    persistent SDK client for the lifetime of a chat session, giving Claude
    real conversational memory across multiple queries.

    Lifecycle::

        session = ClaudeSession(...)
        await session.start()       # opens the SDK client
        async for event in session.send_message("hi"):
            ...                     # StreamToken / StreamResult / etc.
        async for event in session.send_message("follow-up"):
            ...                     # Claude remembers "hi"
        await session.stop()        # closes the SDK client
    """

    def __init__(
        self,
        cli_path: str = "claude",
        session_id: str | None = None,
        fork_session: bool = False,
        model: str | None = None,
        cwd: str | None = None,
        permission_mode: str = "acceptEdits",
        allowed_tools: list[str] | None = None,
    ) -> None:
        self._cli_path = cli_path
        self._session_id = session_id
        self._fork_session = fork_session
        self._model = model
        self._cwd = cwd or os.getcwd()
        self._permission_mode = permission_mode
        self._allowed_tools = allowed_tools or list(DEFAULT_TOOLS)

        self._client: ClaudeSDKClient | None = None
        self._captured_session_id: str | None = None
        self._ready = asyncio.Event()
        self._start_error: str | None = None

    async def start(self) -> None:
        """Open the SDK client.

        Sets ``_ready`` when done so that ``send_message`` can wait for
        initialization without blocking the Textual event loop.
        """
        try:
            opts = ClaudeAgentOptions(
                cli_path=self._cli_path,
                cwd=self._cwd,
                allowed_tools=self._allowed_tools,
                permission_mode=self._permission_mode,
                model=self._model,
                resume=self._session_id,
                fork_session=self._fork_session,
                # Prevent "cannot launch inside another Claude Code session" error
                env={"CLAUDECODE": ""},
            )
            self._client = ClaudeSDKClient(options=opts)
            await self._client.connect()
            log.info(
                "ClaudeSession started (resume=%s, fork=%s)",
                self._session_id,
                self._fork_session,
            )
        except Exception as exc:
            self._start_error = str(exc)
            log.error("ClaudeSession failed to start: %s", exc)
        finally:
            self._ready.set()

    async def stop(self) -> None:
        """Close the SDK client gracefully."""
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None
        log.info("ClaudeSession stopped")

    async def send_message(
        self,
        prompt: str,
        session_id: str | None = None,
        reply_context: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Send a message and yield streaming events.

        The signature intentionally matches ``ClaudeProcess.send_message()``
        for drop-in compatibility.  The ``session_id`` parameter is accepted
        but ignored — the SDK client already knows its session.
        """
        # Wait for start() to finish (it runs as a background task)
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            yield StreamError(message="Claude session timed out during initialization")
            return

        if self._start_error:
            yield StreamError(message=f"Claude session failed to start: {self._start_error}")
            return

        if self._client is None:
            yield StreamError(message="ClaudeSession not started")
            return

        full_prompt = prompt
        if reply_context:
            full_prompt = f'[Regarding your earlier message: "{reply_context}"]\n\n{prompt}'

        # Switch model if the caller requests a different one
        if model and model != self._model:
            self._model = model
            try:
                self._client.set_model(model)
            except Exception:
                pass

        try:
            await self._client.query(full_prompt)

            full_content_parts: list[str] = []
            last_model: str | None = None

            async for msg in self._client.receive_response():
                if isinstance(msg, AssistantMessage):
                    # Capture model from the assistant message itself
                    if msg.model:
                        last_model = msg.model
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            text = block.text
                            if text:
                                full_content_parts.append(text)
                                yield StreamToken(text=text)

                elif isinstance(msg, ResultMessage):
                    # Capture the session ID from the SDK
                    if msg.session_id and msg.session_id != self._captured_session_id:
                        self._captured_session_id = msg.session_id
                        yield StreamSessionId(session_id=msg.session_id)

                    # Extract usage stats — handle both flat and nested formats
                    input_tokens = None
                    output_tokens = None
                    if msg.usage:
                        # Flat format: {"input_tokens": N, "output_tokens": N}
                        if "input_tokens" in msg.usage:
                            input_tokens = msg.usage.get("input_tokens")
                            output_tokens = msg.usage.get("output_tokens")
                        else:
                            # Nested format: {"model-name": {"inputTokens": N}}
                            for _m, usage in msg.usage.items():
                                if isinstance(usage, dict):
                                    input_tokens = usage.get("inputTokens")
                                    output_tokens = usage.get("outputTokens")
                                    if not last_model:
                                        last_model = _m
                                break

                    yield StreamResult(
                        content=msg.result or "".join(full_content_parts),
                        session_id=msg.session_id,
                        cost_usd=msg.total_cost_usd,
                        duration_ms=msg.duration_ms,
                        model=last_model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )

        except Exception as exc:
            log.exception("ClaudeSession error: %s", exc)
            yield StreamError(message=str(exc))

    def cancel(self) -> None:
        """Interrupt the current response."""
        if self._client is not None:
            try:
                self._client.interrupt()
            except Exception:
                pass

    def set_model(self, model: str | None) -> None:
        """Switch the model for subsequent queries."""
        self._model = model
        if self._client is not None and model is not None:
            try:
                self._client.set_model(model)
            except Exception:
                pass

    @property
    def session_id(self) -> str | None:
        """The SDK session ID, captured from the first ``ResultMessage``."""
        return self._captured_session_id
