from app.core.llm_client import DeepSeekLLMClient


class _Response:
    def __init__(self, status_code: int, content: str = "ok"):
        self.status_code = status_code
        self.headers = {}
        self._content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeHTTPX:
    class TimeoutException(Exception):
        pass

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def post(self, *args, **kwargs):
        response = self.responses[self.calls]
        self.calls += 1
        return response


def _client(fake_httpx) -> DeepSeekLLMClient:
    client = DeepSeekLLMClient.__new__(DeepSeekLLMClient)
    client._httpx = fake_httpx
    client.base_url = "https://example.invalid"
    client.api_key = "test-only"
    client.model = "test"
    client.max_attempts = 3
    client.backoff_base_s = 0
    return client


def test_deepseek_retries_429_then_returns_success():
    transport = _FakeHTTPX([_Response(429), _Response(200, "recovered")])
    client = _client(transport)

    assert client._call("system", "user") == "recovered"
    assert transport.calls == 2


def test_deepseek_does_not_retry_non_transient_400():
    transport = _FakeHTTPX([_Response(400), _Response(200)])
    client = _client(transport)

    try:
        client._call("system", "user")
    except RuntimeError as exc:
        assert "400" in str(exc)
    else:
        raise AssertionError("400 must fail")
    assert transport.calls == 1

