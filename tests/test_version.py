from django.test import Client

from biodb import __version__


def test_version():
    response = Client().get("/version/")
    assert response.status_code == 200
    assert __version__
    assert __version__ in response.content.decode()
