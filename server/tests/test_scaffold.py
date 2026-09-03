from fastapi import FastAPI

from app.main import app


def test_scaffold_assembles_a_fastapi_app() -> None:
    assert isinstance(app, FastAPI)
