import pytest

from pragmas_sdk import PragmasClient


@pytest.fixture
def client():
    c = PragmasClient(base_url="https://api.pragmas.io", beta_key="pk_beta_test")
    yield c
    c.close()


@pytest.fixture
def anon_client():
    """A client with no beta key set, for auth-error tests."""
    c = PragmasClient(base_url="https://api.pragmas.io")
    yield c
    c.close()
