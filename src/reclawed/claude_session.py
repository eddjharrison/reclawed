"""Persistent Claude session using the Agent SDK.

Replaces the subprocess-per-prompt ``ClaudeProcess`` with a long-lived
``ClaudeSDKClient`` that maintains real conversation context across
multiple queries within a session.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from typing import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from reclawed.claude import (
    StreamError, StreamEvent, StreamResult, StreamSessionId,
    StreamToken, StreamToolResult, StreamToolUse,
)

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
        approval_callback=None,
    ) -> None:
        self._cli_path = cli_path
        self._session_id = session_id
        self._fork_session = fork_session
        self._model = model
        self._cwd = cwd or os.getcwd()
        self._permission_mode = permission_mode
        self._allowed_tools = allowed_tools or list(DEFAULT_TOOLS)
        # Callback for tool approval: async (tool_name, tool_input, future) -> None
        self._approval_callback = approval_callback

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
            kwargs: dict = {
                "cli_path": self._cli_path,
                "cwd": self._cwd,
                "allowed_tools": self._allowed_tools,
                "permission_mode": self._permission_mode,
                "model": self._model,
                "resume": self._session_id,
                "fork_session": self._fork_session,
                "env": {"CLAUDECODE": ""},
            }
            # Wire tool approval callback if we have one and aren't bypassing
            if self._approval_callback and self._permission_mode != "bypassPermissions":
                kwargs["can_use_tool"] = self._handle_tool_permission
            opts = ClaudeAgentOptions(**kwargs)
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
        attachments: list[str] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Send a message and yield streaming events.

        The signature intentionally matches ``ClaudeProcess.send_message()``
        for drop-in compatibility.  The ``session_id`` parameter is accepted
        but ignored — the SDK client already knows its session.

        If *attachments* is provided (list of file paths), the prompt is sent
        as multimodal content with image blocks.
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
            # Build the query — multimodal if we have image attachments
            if attachments:
                query_input = self._build_multimodal_message(full_prompt, attachments)
                await self._client.query(query_input)
            else:
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
                        elif isinstance(block, ToolUseBlock):
                            yield StreamToolUse(
                                tool_use_id=block.id,
                                tool_name=block.name,
                                tool_input=block.input,
                            )
                        elif isinstance(block, ToolResultBlock):
                            content = block.content
                            if isinstance(content, list):
                                content = str(content)
                            yield StreamToolResult(
                                tool_use_id=block.tool_use_id,
                                content=content,
                                is_error=bool(block.is_error),
                            )

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

    async def _handle_tool_permission(self, tool_name, tool_input, context):
        """SDK callback — pauses execution until the TUI approves or denies."""
        if self._approval_callback is None:
            return PermissionResultAllow()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        try:
            await self._approval_callback(tool_name, tool_input, future)
            result = await asyncio.wait_for(future, timeout=300)
            return result
        except asyncio.TimeoutError:
            log.warning("Tool approval timed out for %s, auto-allowing", tool_name)
            return PermissionResultAllow()
        except Exception as exc:
            log.error("Tool approval error: %s", exc)
            return PermissionResultAllow()

    @staticmethod
    def _build_multimodal_message(
        text: str, attachments: list[str],
    ) -> str:
        """Build a multimodal prompt string with image file references.

        The Claude Code CLI accepts file paths prefixed with the image
        reference syntax.  We encode images as base64 data URIs embedded
        in the prompt text, which the CLI forwards to the API.

        For now, we prepend file references so the CLI's built-in handling
        can pick them up.  If the SDK adds native image block support in
        the future, this method should be updated.
        """
        from reclawed.utils import get_image_mime

        parts: list[str] = []
        for path in attachments:
            p = Path(path)
            if p.exists() and p.is_file():
                mime = get_image_mime(p)
                b64 = base64.standard_b64encode(p.read_bytes()).decode("ascii")
                # Use data URI format that Claude Code recognizes
                parts.append(f"![image](<data:{mime};base64,{b64}>)")

        if parts:
            image_refs = "\n\n".join(parts)
            return f"{image_refs}\n\n{text}"
        return text

    @property
    def session_id(self) -> str | None:
        """The SDK session ID, captured from the first ``ResultMessage``."""
        return self._captured_session_id
