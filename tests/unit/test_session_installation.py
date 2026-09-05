"""Installation persistence with the supported Peewee model API."""

import logging

from peewee import SqliteDatabase

from compresso.libs.session import Session
from compresso.libs.unmodels import Installation


def test_session_creates_and_reuses_installation():
    database = SqliteDatabase(":memory:")
    with database.bind_ctx([Installation]), database.connection_context():
        database.create_tables([Installation])
        first = object.__new__(Session)
        first.logger = logging.getLogger(__name__)
        first._Session__fetch_installation_data()

        second = object.__new__(Session)
        second.logger = logging.getLogger(__name__)
        second._Session__fetch_installation_data()

        assert Installation.select().count() == 1
        assert first.uuid == second.uuid == str(Installation.get().uuid)
        assert first.created == second.created
        assert first.level == second.level == 100
