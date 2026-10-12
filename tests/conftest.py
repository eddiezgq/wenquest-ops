"""Shared fixtures. Database tests need PostgreSQL: set WQO_TEST_DB (CI always does)."""

import os

import pytest

from wqops.hub import db as DB


@pytest.fixture
def db_url():
    url = os.environ.get("WQO_TEST_DB")
    if not url:
        if os.environ.get("CI"):
            pytest.fail("WQO_TEST_DB must be set in CI")
        pytest.skip("set WQO_TEST_DB to run database tests")
    with DB.connect(url) as c:
        c.execute("drop schema public cascade")
        c.execute("create schema public")
    return url


@pytest.fixture
def conn(db_url):
    c = DB.connect(db_url)
    DB.migrate(c)
    yield c
    c.close()
