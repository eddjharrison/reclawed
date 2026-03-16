"""Claude CLI subprocess management and stream-json parsing."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator

log = logging.getLogger(__name__)

SESSION_LOCK_ERROR = "already in use"


@dataclass
class StreamToken:
    """A chunk of text from Claude's streaming response."""
    text: str


@dataclass
class StreamResult:
    """Final result from a Claude response."""
    content: str
    session_id: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class StreamError:
    """Error from the Claude subprocess."""
    message: str


@dataclass
class StreamSessionId:
    """Emitted when we capture the session ID from Claude."""
    session_id: str


@dataclass
class StreamToolUse:
    """Claude is invoking a tool."""
    tool_use_id: str
    tool_name: str
    tool_input: dict


@dataclass
class StreamToolResult:
    """Tool execution completed."""
    tool_use_id: str
    content: str | None
    is_error: bool


StreamEvent = (
    StreamToken | StreamResult | StreamError | StreamSessionId
    | StreamToolUse | StreamToolResult
)


class ClaudeProcess:
    """Manages a Claude CLI subprocess and parses stream-json output."""

    def __init__(self, claude_binary: str = "claude"):
        self._binary = claude_binary
        self._process: asyncio.subprocess.Process | None = None

    async def send_message(
        self,
        prompt: str,
        session_id: str | None = None,
        reply_context: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Send a message to Claude and yield streaming events.

        If the session is locked, automatically retries without --session-id.

        Args:
            prompt: The user message to send.
            session_id: Claude session ID for conversation continuity.
            reply_context: Optional quoted context prepended to the prompt.
            model: Optional model override (e.g. "sonnet", "opus", "haiku").
                   Passed as ``--model <model>`` to the CLI when provided.
        """
        full_prompt = prompt
        if reply_context:
            full_prompt = f'[Regarding your earlier message: "{reply_context}"]\n\n{prompt}'

        # Try with session_id first, fall back without if locked
        use_session_id = session_id
        for attempt in range(2):
            cmd = [
                self._binary, "-p", full_prompt,
                "--output-format", "stream-json",
                "--verbose",
            ]
            if use_session_id:
                cmd.extend(["--session-id", use_session_id])
            if model:
                cmd.extend(["--model", model])

            log.debug("Spawning (attempt %d): %s", attempt + 1, " ".join(cmd[:6]))

            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=16 * 1024 * 1024,  # 16MB — Claude result lines can be very long
            )

            captured_session_id: str | None = None
            full_content_parts: list[str] = []
            got_content = False
            session_locked = False

            async for line in self._read_lines():
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    log.warning("Non-JSON line from claude: %s", line[:200])
                    continue

                event_type = event.get("type")

                if event_type == "system":
                    sid = event.get("session_id")
                    if sid:
                        captured_session_id = sid
                        yield StreamSessionId(session_id=sid)

                elif event_type == "assistant":
                    msg = event.get("message", {})
                    for block in msg.get("content", []):
                        if block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                got_content = True
                                full_content_parts.append(text)
                                yield StreamToken(text=text)

                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            got_content = True
                            full_content_parts.append(text)
                            yield StreamToken(text=text)

                elif event_type == "result":
                    got_content = True
                    result_content = event.get("result", "")
                    cost = event.get("total_cost_usd")
                    duration = event.get("duration_ms")
                    model_usage = event.get("modelUsage", {})
                    model_name = None
                    input_tok = None
                    output_tok = None
                    for m, usage in model_usage.items():
                        model_name = m
                        input_tok = usage.get("inputTokens")
                        output_tok = usage.get("outputTokens")
                        break

                    yield StreamResult(
                        content=result_content or "".join(full_content_parts),
                        session_id=captured_session_id,
                        cost_usd=cost,
                        duration_ms=duration,
                        model=model_name,
                        input_tokens=input_tok,
                        output_tokens=output_tok,
                    )

            # Wait for process to fully terminate and release session lock
            await self._process.wait()

            # Check for session lock error
            if self._process.returncode and self._process.returncode != 0:
                stderr = b""
                if self._process.stderr:
                    stderr = await self._process.stderr.read()
                stderr_text = stderr.decode()[:500]

                if SESSION_LOCK_ERROR in stderr_text and use_session_id and attempt == 0:
                    log.warning("Session locked, retrying without --session-id")
                    use_session_id = None
                    session_locked = True
                    # Brief pause to let any lock release
                    await asyncio.sleep(0.5)
                    continue
                elif not got_content:
                    yield StreamError(message=f"Claude exited with code {self._process.returncode}: {stderr_text}")

            # Success or non-retryable error — done
            break

    async def _read_lines(self) -> AsyncIterator[str]:
        """Read lines from the subprocess stdout."""
        assert self._process and self._process.stdout
        while True:
            line = await self._process.stdout.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace")

    def cancel(self) -> None:
        """Kill the running subprocess."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
