#!/usr/bin/env python3

"""
compresso.__init__.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     10 Sep 2019, (8:06 PM)

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

import inspect
import os
import pkgutil
import sys
from importlib import import_module
from pathlib import Path

from ..base_containers import ContainerDescription, Containers


def grab_module(module_name: str) -> Containers:
    """
    Fetch a module by name and return the instance of that class

    :param module_name:
    :param args:
    :param kwargs:
    :return:
    """
    try:
        if "." in module_name:
            module_name, class_name = module_name.rsplit(".", 1)
        else:
            class_name = module_name.capitalize()

        module = import_module("." + module_name, package=__name__)
        module_class = getattr(module, class_name)
        if not isinstance(module_class, type) or not issubclass(module_class, Containers):
            raise AttributeError(class_name)
        return module_class()

    except (AttributeError, AssertionError, ModuleNotFoundError):
        raise ImportError(f"{module_name} is not part of our supported containers!") from None


def get_all_containers() -> dict[str, ContainerDescription]:
    """
    Fetch a list of supported containers and
    return a dictionary of their data

    :return:
    """
    containers_dic: dict[str, ContainerDescription] = {}

    for _finder, module_name, _is_package in pkgutil.iter_modules([os.path.join(Path(__file__).parent)]):
        instance = grab_module(module_name)
        container_data = ContainerDescription(
            extension=instance.container_extension(),
            description=instance.container_description(),
            supports_subtitles=instance.container_supports_subtitles(),
        )
        containers_dic[module_name] = container_data

    return containers_dic


"""
Import all submodules for this package

"""
for _finder, discovered_name, _is_package in pkgutil.iter_modules([os.path.join(Path(__file__).parent)]):
    imported_module = import_module("." + discovered_name, package=__name__)

    for i in dir(imported_module):
        attribute = getattr(imported_module, i)

        if inspect.isclass(attribute) and issubclass(attribute, Containers):
            setattr(sys.modules[__name__], discovered_name, attribute)

__author__ = "Josh.5 (jsunnex@gmail.com)"

__all__ = ("Containers",)
