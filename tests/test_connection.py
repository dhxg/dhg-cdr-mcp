import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from core.connection import ConnectionConfig, CorelDrawConnection


class FailingThread:
    def __init__(self, error):
        self.error = error
        self.calls = 0
    def call(self, *args, **kwargs):
        self.calls += 1
        raise self.error


class ConnectionRetryTests(unittest.TestCase):
    def connection_with(self, error):
        conn = object.__new__(CorelDrawConnection)
        conn.config = ConnectionConfig(max_retries=3, reconnect_on_failure=True)
        conn._com_thread = FailingThread(error)
        conn.reconnect = lambda: True
        return conn

    def test_non_idempotent_call_is_never_retried(self):
        conn = self.connection_with(RuntimeError("RPC rejected"))
        result = conn.safe_call(lambda: None, idempotent=False)
        self.assertFalse(result["success"])
        self.assertEqual(conn._com_thread.calls, 1)

    def test_timeout_is_never_retried(self):
        conn = self.connection_with(TimeoutError("slow export"))
        result = conn.safe_call(lambda: None, idempotent=True)
        self.assertFalse(result["success"])
        self.assertEqual(conn._com_thread.calls, 1)


if __name__ == "__main__":
    unittest.main()
