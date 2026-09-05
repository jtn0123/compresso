#!/usr/bin/env python3

"""
compresso.directoryinfo.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     02 Jul 2021, (10:59 AM)

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

import configparser
import json
import os
from typing import cast

from compresso.libs.json_state import atomic_json_write


class CompressoDirectoryInfoException(Exception):
    def __init__(self, message: str, path: str | os.PathLike[str]) -> None:
        errmsg = f"{message}: file {path}"
        Exception.__init__(self, errmsg)
        self.message = message
        self.path = path

    def __repr__(self) -> str:
        return self.message

    __str__ = __repr__


class CompressoDirectoryInfo:
    """
    CompressoDirectoryInfo

    Manages the reading and writing of the '.compresso' files located in the directories
    parsed by Compresso's library scanner or any plugins.

    Legacy support:
        On read, if the config is an INI file, uses ConfigParser.get to fetch information
        and convert it to JSON.
        INI was initially used in order to be a simple syntax for manually editing.
        However, INI is not ideal for managing file names and paths with special characters

    """

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.path = os.path.join(directory, ".compresso")
        self.json_data: dict[str, dict[str, object]] | None = None
        self.config_parser: configparser.ConfigParser | None = None
        # If the path does not exist, do not try to read it
        if not os.path.exists(self.path):
            self.json_data = {}
            return
        # First read JSON data
        try:
            with open(self.path) as infile:
                self.json_data = self.__parse_json_data(json.load(infile))
            # Migrate JSON to latest formatting
            if self.json_data is not None:
                self.__migrate_json_formatting()
        except json.decoder.JSONDecodeError:
            pass
        # If we were unable to import the JSON data, attempt to read as INI
        if self.json_data is None:
            try:
                self.config_parser = configparser.ConfigParser(allow_no_value=True)
                self.config_parser.read(self.path)
                # Migrate file to JSON
                self.__migrate_to_json()
            except configparser.MissingSectionHeaderError:
                pass
            except configparser.NoSectionError:
                pass
            except configparser.NoOptionError:
                pass
        # If we still do not have JSON data at this point, something has gone wrong
        if self.json_data is None:
            raise CompressoDirectoryInfoException("Failed to read directory info", self.path)

    @staticmethod
    def __parse_json_data(value: object) -> dict[str, dict[str, object]] | None:
        if not isinstance(value, dict) or not all(isinstance(section, str) for section in value):
            return None

        parsed: dict[str, dict[str, object]] = {}
        for section, raw_options in cast("dict[str, object]", value).items():
            if not isinstance(raw_options, dict) or not all(isinstance(key, str) for key in raw_options):
                return None
            parsed[section] = cast("dict[str, object]", raw_options)
        return parsed

    def __migrate_to_json(self) -> None:
        """
        Migrate data from INI to JSON

        :return:
        """
        if self.config_parser is None:
            raise CompressoDirectoryInfoException("Failed to migrate directory info", self.path)
        sections = self.config_parser.sections()
        json_data: dict[str, dict[str, object]] = {}
        for section in sections:
            section_data: dict[str, object] = {}
            for key in self.config_parser[section]:
                section_data[key.lower()] = self.config_parser.get(section, key)
            json_data[section] = section_data
        self.json_data = json_data

    def __migrate_json_formatting(self) -> None:
        """
        Migrate JSON to latest format

        Migration 1:
            As Compresso may be used on platforms that view files as case-insensitive,
            we should ensure that all keys are also stored this way.

        :return:
        """
        # Ensure all keys are lower case
        if self.json_data is None:
            return
        sections = list(self.json_data)
        for section in sections:
            # Sections remain case sensitive, but keys must be lowercase
            keys = [k for k in self.json_data[section]]
            for key in keys:
                if key != key.lower():
                    self.json_data[section][key.lower()] = self.json_data[section][key]
                    del self.json_data[section][key]

    def set(self, section: str, option: str, value: object | None = None) -> None:
        """
        Set an option.

        :param section:
        :param option:
        :param value:
        :return:
        """
        # Ensure keys are always lower-case
        option = option.lower()
        if self.json_data is not None:
            if not self.json_data.get(section):
                self.json_data[section] = {}
            self.json_data[section][option] = value
            return
        elif self.config_parser:
            if not self.config_parser.has_section(section):
                self.config_parser.add_section(section)
            config_value = value if isinstance(value, str) or value is None else str(value)
            self.config_parser.set(section, option, config_value)
            return
        raise CompressoDirectoryInfoException(
            f"Failed to set section '{section}' option '{option}' value '{value}'", self.path
        )

    def get(self, section: str, option: str) -> object | None:
        """
        Get an option

        :param section:
        :param option:
        :return:
        """
        option = option.lower()
        if self.json_data is not None:
            return self.json_data.get(section, {}).get(option)
        elif self.config_parser:
            return self.config_parser.get(section, option)
        raise CompressoDirectoryInfoException(f"Failed to get section '{section}' option '{option}'", self.path)

    def save(self) -> None:
        """
        Saves the data to file.

        :return:
        """
        if self.json_data is not None:
            atomic_json_write(self.path, self.json_data)
            return
        elif self.config_parser:
            with open(self.path, "w") as outfile:
                self.config_parser.write(outfile)
            return
        raise CompressoDirectoryInfoException("Failed to save directory info", self.path)


if __name__ == "__main__":
    directory_info = CompressoDirectoryInfo("/tmp/compresso")  # noqa: S108 — dev test block
    directory_info.set("test_section", "key", "value")
    directory_info.save()
    print(directory_info.get("test_section", "key"))  # noqa: T201
    directory_info.set('"section with double quotes"', '"key with double quotes"', '"value with double quotes"')
    directory_info.save()
    print(directory_info.get('"section with double quotes"', '"key with double quotes"'))  # noqa: T201
