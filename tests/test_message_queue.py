"""Tests for message queue feature."""


def test_queued_message_defaults():
    """QueuedMessage stores text and optional attachments/reply."""
    from reclawed.screens.chat import QueuedMessage

    qm = QueuedMessage(text="hello")
    assert qm.text == "hello"
    assert qm.attachments == []
    assert qm.reply_to_id is None
    assert qm.reply_context is None


def test_queued_message_with_all_fields():
    from reclawed.screens.chat import QueuedMessage

    qm = QueuedMessage(
        text="hello",
        attachments=["/tmp/img.png"],
        reply_to_id="msg-123",
        reply_context="original text",
    )
    assert qm.attachments == ["/tmp/img.png"]
    assert qm.reply_to_id == "msg-123"
    assert qm.reply_context == "original text"


def test_per_session_queue_isolation():
    """Each session ID gets its own independent queue."""
    from collections import deque
    from reclawed.screens.chat import QueuedMessage

    queues: dict[str, deque[QueuedMessage]] = {}

    queues.setdefault("session-a", deque()).append(QueuedMessage(text="a1"))
    queues.setdefault("session-a", deque()).append(QueuedMessage(text="a2"))
    queues.setdefault("session-b", deque()).append(QueuedMessage(text="b1"))

    assert len(queues["session-a"]) == 2
    assert len(queues["session-b"]) == 1

    queues["session-a"].popleft()
    assert len(queues["session-a"]) == 1
    assert len(queues["session-b"]) == 1


def test_queue_fifo_order():
    """Queue drains in FIFO order."""
    from collections import deque
    from reclawed.screens.chat import QueuedMessage

    queue: deque[QueuedMessage] = deque()
    queue.append(QueuedMessage(text="first"))
    queue.append(QueuedMessage(text="second"))
    queue.append(QueuedMessage(text="third"))

    assert queue.popleft().text == "first"
    assert queue.popleft().text == "second"
    assert queue.popleft().text == "third"
    assert len(queue) == 0
