#!/usr/bin/env python3

"""
compresso.singleton.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     26 Oct 2020, (2:51 PM)

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

import threading
from typing import cast

lock = threading.RLock()


class SingletonType(type):
    """Singleton metaclass"""

    _instances: dict[type[object], object] = {}

    def __call__[T](cls: type[T], *args: object, **kwargs: object) -> T:
        if cls not in SingletonType._instances:
            with lock:
                if cls not in SingletonType._instances:
                    SingletonType._instances[cls] = type.__call__(cls, *args, **kwargs)
                    return cast("T", SingletonType._instances[cls])
        if args or kwargs:
            # Constructor arguments after the first instantiation would be
            # silently dropped (e.g. Config(port=...) after an earlier bare
            # Config()), making initialization order an invisible, load-bearing
            # dependency. Fail loudly instead.
            raise RuntimeError(
                f"{cls.__name__} is a singleton and is already instantiated; "
                "constructor arguments passed now would be ignored. "
                "Construct it with arguments once, before any other use."
            )
        return cast("T", SingletonType._instances[cls])
