import pytest

from api.model_client import ModelServerClient, ModelServerError


class Resp:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload


class Session:
    def __init__(self, payload): self.payload = payload
    def post(self, *a, **k): return Resp(self.payload)


def test_prediction_count_must_match_row_count():
    short = ModelServerClient("http://x", session=Session({"predictions": [[0.4, 0.6]]}))
    with pytest.raises(ModelServerError, match="expected 2 predictions, got 1"):
        short.predict_proba(["a"], [[1], [2]])


def test_matching_count_still_works():
    ok = ModelServerClient("http://x", session=Session({"predictions": [[0.4, 0.6], [0.7, 0.3]]}))
    assert ok.predict_proba(["a"], [[1], [2]]) == [0.6, 0.3]
