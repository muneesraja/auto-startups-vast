import threading
import time

import config
from tools import grok_replicate
from tools import image_pipeline


def test_run_image_jobs_limits_concurrency(monkeypatch):
    monkeypatch.setattr(config, "REPLICATE_IMAGE_CONCURRENCY", 2)
    lock = threading.Lock()
    active = 0
    peak = 0

    def job(value):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return value

    assert image_pipeline.run_image_jobs([lambda value=value: job(value) for value in range(4)]) == [0, 1, 2, 3]
    assert peak == 2


def test_run_prediction_retries_throttling(monkeypatch):
    class Client:
        def __init__(self):
            self.calls = 0

        def run(self, _model, input):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("429 Request was throttled")
            return input

    client = Client()
    monkeypatch.setattr(grok_replicate, "_MAX_RETRIES", 1)
    monkeypatch.setattr(grok_replicate, "_throttle", lambda: None)
    monkeypatch.setattr(grok_replicate.time, "sleep", lambda _seconds: None)

    assert grok_replicate._run_prediction(client, "model", {"prompt": "test"}) == {"prompt": "test"}
    assert client.calls == 2
