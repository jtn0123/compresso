#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.libraryanalysiscache.py

    Cache table for library analysis results (codec distribution,
    estimated savings, etc.).

"""

from peewee import *
from compresso.libs.unmodels.lib import BaseModel


class LibraryAnalysisCache(BaseModel):
    """
    LibraryAnalysisCache

    Stores cached library analysis results per library.
    """
    library_id = IntegerField(index=True)
    analysis_json = TextField(default='{}')
    file_count = IntegerField(default=0)
    last_run = DateTimeField(null=True)
    version = IntegerField(default=0)
