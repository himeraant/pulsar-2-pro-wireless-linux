"""Shared mock device for engine tests (feature_out / feature_in)."""


class MockDevice:
    """Replays canned feature-report responses; records feature_out calls."""

    def __init__(self):
        self.feature_out_calls = []
        # report_id -> list[bytes] responses (FIFO per report id)
        self.feature_in_responses = {}

    def feature_out(self, report_id: int, data: bytes) -> None:
        self.feature_out_calls.append((report_id, bytes(data)))

    def feature_in(self, report_id: int, size: int) -> bytes:
        resp = self.feature_in_responses[report_id].pop(0)
        return bytes(resp)

    def enqueue(self, report_id: int, response: bytes) -> "MockDevice":
        self.feature_in_responses.setdefault(report_id, []).append(bytes(response))
        return self
