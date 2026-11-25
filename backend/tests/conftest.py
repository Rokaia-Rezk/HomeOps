import os, tempfile, pytest
_d = tempfile.mkdtemp()
os.environ["HOMEOPS_DB"] = os.path.join(_d, "t.db")
os.environ["HOMEOPS_SECRET"] = "test-secret-test-secret-test-secret-123"
os.environ["HOMEOPS_SEED_EMAIL"] = "boss@example.com"
os.environ["HOMEOPS_SEED_PASSWORD"] = "Boss@12345"
os.environ["HOMEOPS_DEV_OTP"] = "0"
from fastapi.testclient import TestClient
from server.main import app


@pytest.fixture(scope="session")
def c():
    with TestClient(app) as cl:
        yield cl
