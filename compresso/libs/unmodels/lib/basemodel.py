#!/usr/bin/env python3

"""
compresso.basemodel.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     22 Jun 2019, (1:58 PM)

Copyright:
       Copyright (C) Josh Sunnex - All Rights Reserved

       Permission is hereby granted, free of charge, to any person obtaining a copy
       of this software and associated documentation files (the "Software"), to deal
       in the Software without restriction, including without limitation the rights
       to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
       copies of the Software, and to permit persons to whom the Software is
       furnished to do so, subject to the following conditions:

       The above copyright notice and this permission notice shall be included in all
       copies or substantial portions of the Software.

       THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
       EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
       MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
       IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
       DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
       OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
       OR OTHER DEALINGS IN THE SOFTWARE.

"""

import logging
from base64 import b64decode
from datetime import date, datetime, time
from typing import TypedDict, cast

from peewee import (
    AutoField,
    BlobField,
    BooleanField,
    DatabaseProxy,
    DateField,
    DateTimeField,
    DecimalField,
    FloatField,
    IntegerField,
    Model,
    TimeField,
)

from compresso.libs.peewee_types import create_sqlite_queue_database, model_as_dict

logger = logging.getLogger(__name__)

# Do not initialise the database until the model is called.

db = DatabaseProxy()  # Create a proxy for our db.

# Stipulate date and time formats
DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M:%S"
TIME_FORMAT_ALT = f"{TIME_FORMAT}.%f"
DATETIME_BASE = "{}T{}"
DATETIME_FORMAT = DATETIME_BASE.format(DATE_FORMAT, TIME_FORMAT)
DATETIME_FORMAT_ALT = DATETIME_BASE.format(DATE_FORMAT, TIME_FORMAT_ALT)


class DatabaseConfig(TypedDict):
    TYPE: str
    FILE: str


def strpdatetime(string: str | None) -> datetime | None:
    """
    Parses the datetime from a string.

    """
    if string is not None:
        try:
            return datetime.strptime(string, DATETIME_FORMAT)
        except ValueError:
            return datetime.strptime(string, DATETIME_FORMAT_ALT)
    return None


def strpdate(string: str | None) -> date | None:
    """
    Parses the date from a string.

    """
    if string is not None:
        return datetime.strptime(string, DATE_FORMAT).date()
    return None


def strptime(string: str | None) -> time | None:
    """
    Parses the time from a string.

    """
    if string is not None:
        try:
            return datetime.strptime(string, TIME_FORMAT).time()
        except ValueError:
            return datetime.strptime(string, TIME_FORMAT_ALT).time()
    return None


class NoSuchFieldError(TypeError):
    """
    Indicates that the field does not exist in this model

    """


class NullError(TypeError):
    """
    Indicates that the respective field was set to NULL but must not be NULL.

    """


class Database:
    """
    Database

    Select a database to connect to
    """

    @staticmethod
    def select_database(config: DatabaseConfig) -> DatabaseProxy:
        existing_database = getattr(db, "obj", None)
        if existing_database is not None:
            try:
                if hasattr(existing_database, "is_stopped") and not existing_database.is_stopped():
                    existing_database.stop()
            except Exception as e:
                logger.debug("Failed to stop existing database: %s", e)

            try:
                if hasattr(existing_database, "is_closed") and not existing_database.is_closed():
                    existing_database.close()
            except Exception as e:
                logger.debug("Failed to close existing database: %s", e)

        # Based on configuration, use a different database.
        if config["TYPE"] == "SQLITE":
            # use SqliteQueueDatabase
            database = create_sqlite_queue_database(
                config["FILE"],
                use_gevent=False,
                autostart=True,
                queue_max_size=None,
                results_timeout=15.0,
                pragmas=(
                    ("foreign_keys", 1),
                    ("journal_mode", "wal"),
                ),
            )

            db.initialize(database)
            db.connect()
        return db


class BaseModel(Model):
    """
    BaseModel

    Generic configuration and methods used across all Model classes
    """

    id = AutoField()

    class Meta:
        database = db

    def get_fields(self) -> dict[str, object]:
        """
        Return a dictionary of this models field metadata

        :return:
        """
        return cast("dict[str, object]", self._meta.fields)

    def get_current_field_values_dict(self) -> dict[str, object]:
        """
        Return a dictionary of this models fields and their current values

        :return:
        """
        return cast("dict[str, object]", self.__data__)

    def parse_field_value_by_type(self, field_id: str, value: object) -> object:
        """
        Fetches the field type for this field.
        Return the passed value with the correct type.

        :param field_id:
        :param value:
        :return:
        """
        model_fields = self.get_fields()

        if field_id not in model_fields:
            raise NoSuchFieldError()

        # Set the field from model
        field = model_fields[field_id]

        if value is None:
            if not getattr(field, "null", False):
                raise NullError()
            return value

        if isinstance(field, BooleanField):
            if isinstance(value, (bool, int)):
                return bool(value)
            elif isinstance(value, str) and value.lower() in ["t", "true", "1"]:
                return True
            elif isinstance(value, str) and value.lower() in ["f", "false", "0"]:
                return False
            # Unrecognised values must fail loudly, not coerce to False
            raise TypeError(f"Cannot interpret {value!r} as a boolean for field '{field_id}'")
        elif isinstance(field, IntegerField):
            return int(cast("str | bytes | bytearray | float | int", value))
        elif isinstance(field, (FloatField, DecimalField)):
            return float(cast("str | bytes | bytearray | float | int", value))
        elif isinstance(field, DateTimeField):
            return strpdatetime(value if isinstance(value, str) else str(value))
        elif isinstance(field, DateField):
            return strpdate(value if isinstance(value, str) else str(value))
        elif isinstance(field, TimeField):
            return strptime(value if isinstance(value, str) else str(value))
        elif isinstance(field, BlobField):
            if not isinstance(value, (str, bytes, bytearray)):
                raise TypeError("Blob field values must be base64 text or bytes")
            return b64decode(value)

        return value

    def model_to_dict(self) -> dict[str, object]:
        """
        Retrieve all related objects recursively and
        then converts the resulting objects to a dictionary.

        :return:
        """
        return model_as_dict(self, backrefs=True)
