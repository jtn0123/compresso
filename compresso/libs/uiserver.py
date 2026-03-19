#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.uiserver.py

    Written by:               Josh.5 <jsunnex@gmail.com>
    Date:                     06 Dec 2018, (7:21 AM)

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
import asyncio
import os
import socket
import threading
import logging

import tornado.httpserver
import tornado.ioloop
import tornado.routing
import tornado.template
import tornado.web

from compresso import config
from compresso.libs import common
from compresso.libs.logs import CompressoLogging
from compresso.libs.singleton import SingletonType
from compresso.libs.startup import StartupState
from compresso.webserver.downloads import DownloadsHandler

public_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "webserver", "public"))
tornado_settings = {
    'template_loader': tornado.template.Loader(public_directory),
    'static_css':      os.path.join(public_directory, "css"),
    'static_fonts':    os.path.join(public_directory, "fonts"),
    'static_icons':    os.path.join(public_directory, "icons"),
    'static_img':      os.path.join(public_directory, "img"),
    'static_js':       os.path.join(public_directory, "js"),
    'debug':           True,
    'autoreload':      False,
}


class CompressoDataQueues(object, metaclass=SingletonType):
    _compresso_data_queues = {}

    def __init__(self):
        pass

    def set_compresso_data_queues(self, compresso_data_queues):
        self._compresso_data_queues = compresso_data_queues

    def get_compresso_data_queues(self):
        return self._compresso_data_queues


class CompressoRunningThreads(object, metaclass=SingletonType):
    _compresso_threads = {}

    def __init__(self):
        pass

    def set_compresso_running_threads(self, compresso_threads):
        self._compresso_threads = compresso_threads

    def get_compresso_running_thread(self, name):
        return self._compresso_threads.get(name)


class UIServer(threading.Thread):
    config = None
    started = False
    io_loop = None
    server = None
    app = None

    def __init__(self, compresso_data_queues, foreman, developer):
        super(UIServer, self).__init__(name='UIServer')
        self.config = config.Config()
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)

        self.developer = developer
        self.data_queues = compresso_data_queues
        self.inotifytasks = compresso_data_queues["inotifytasks"]
        # TODO: Move all logic out of template calling to foreman.
        #  Create methods here to handle the calls and rename to foreman
        self.foreman = foreman
        self.set_logging()
        # Add a singleton for handling the data queues for sending data to compresso's other processes
        udq = CompressoDataQueues()
        udq.set_compresso_data_queues(compresso_data_queues)
        urt = CompressoRunningThreads()
        urt.set_compresso_running_threads(
            {
                'foreman': foreman
            }
        )

    def _log(self, message, message2='', level="info"):
        message = common.format_message(message, message2)
        getattr(self.logger, level)(message)

    def stop(self):
        if self.started:
            self.started = False
        if self.io_loop:
            self.io_loop.add_callback(self.io_loop.stop)
            self.io_loop.close(True)

    def set_logging(self):
        if self.config and self.config.get_log_path():
            # Create directory if not exists
            if not os.path.exists(self.config.get_log_path()):
                os.makedirs(self.config.get_log_path())

            # Create file handler
            log_file = os.path.join(self.config.get_log_path(), 'tornado.log')
            file_handler = logging.handlers.TimedRotatingFileHandler(log_file, when='midnight', interval=1,
                                                                     backupCount=7)
            file_handler.setLevel(logging.INFO)

            # Set tornado.access logging to file. Disable propagation of logs
            tornado_access = logging.getLogger("tornado.access")
            if self.developer:
                tornado_access.setLevel(logging.DEBUG)
            else:
                tornado_access.setLevel(logging.INFO)
            tornado_access.addHandler(file_handler)
            tornado_access.propagate = False

            # Set tornado.application logging to file. Enable propagation of logs
            tornado_application = logging.getLogger("tornado.application")
            if self.developer:
                tornado_application.setLevel(logging.DEBUG)
            else:
                tornado_application.setLevel(logging.INFO)
            tornado_application.addHandler(file_handler)
            tornado_application.propagate = True  # Send logs also to root logger (command line)

            # Set tornado.general logging to file. Enable propagation of logs
            tornado_general = logging.getLogger("tornado.general")
            if self.developer:
                tornado_general.setLevel(logging.DEBUG)
            else:
                tornado_general.setLevel(logging.INFO)
            tornado_general.addHandler(file_handler)
            tornado_general.propagate = True  # Send logs also to root logger (command line)

    def update_tornado_settings(self):
        # Check if this is a development environment or not
        if self.developer:
            tornado_settings['autoreload'] = True
            tornado_settings['serve_traceback'] = True

    def run(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.started = True

        try:
            # Configure tornado server based on config
            self.update_tornado_settings()

            # Load the app
            self.app = self.make_web_app()

            # Configure SSL/TLS if enabled
            ssl_options_config = None
            if self.config.get_ssl_enabled():
                certfile = self.config.get_ssl_certfilepath()
                keyfile = self.config.get_ssl_keyfilepath()

                if certfile and keyfile:
                    # Verify certificate and key files exist
                    if not os.path.exists(certfile):
                        self._log(f"SSL certificate file not found: {certfile}", level="error")
                        raise RuntimeError("SSL certificate file not found: {}".format(certfile))
                    if not os.path.exists(keyfile):
                        self._log(f"SSL key file not found: {keyfile}", level="error")
                        raise RuntimeError("SSL key file not found: {}".format(keyfile))

                    ssl_options_config = {
                        "certfile": certfile,
                        "keyfile": keyfile,
                    }
                    self._log(f"HTTPS enabled on port {self.config.get_ui_port()}", level="info")
                else:
                    self._log("SSL enabled but certificate/key files not provided", level="error")
                    raise RuntimeError("SSL enabled but certificate/key files not provided")

            # Web Server
            self.server = tornado.httpserver.HTTPServer(
                self.app,
                ssl_options=ssl_options_config,
            )

            self.server.listen(int(self.config.get_ui_port()), address=self.config.get_ui_address())
            StartupState().mark_ready(
                'ui_server_ready',
                detail="{}:{}".format(self.config.get_ui_address() or '0.0.0.0', self.config.get_ui_port()),
            )
            self._log("UI_SERVER_READY port={}".format(self.config.get_ui_port()), level="info")

            self.io_loop = tornado.ioloop.IOLoop.current()
            self.io_loop.start()
        except socket.error as e:
            message = "UI_SERVER_STARTUP_FAILED port={} error={}".format(self.config.get_ui_port(), str(e))
            StartupState().mark_error('ui_server_ready', message)
            self._log(message, level="error")
        except Exception as e:
            message = "UI_SERVER_STARTUP_FAILED error={}".format(str(e))
            StartupState().mark_error('ui_server_ready', message)
            self._log(message, level="error")
        finally:
            self.started = False
            self._log("Leaving UIServer loop...")

    def make_web_app(self):
        # Start with web application routes
        from compresso.webserver.websocket import CompressoWebsocketHandler
        app = tornado.web.Application([
            (r"/compresso/websocket", CompressoWebsocketHandler),
            (r"/compresso/downloads/(.*)", DownloadsHandler),
            (r"/(.*)", tornado.web.RedirectHandler, dict(
                url="/compresso/ui/dashboard/"
            )),
        ], **tornado_settings)

        # Add API routes
        from compresso.webserver.api_request_router import APIRequestRouter
        app.add_handlers(r'.*', [
            (
                tornado.routing.PathMatches(r"/compresso/api/.*"),
                APIRequestRouter(app)
            ),
        ])

        # Add frontend routes
        from compresso.webserver.main import MainUIRequestHandler
        app.add_handlers(r'.*', [
            (r"/compresso/css/(.*)", tornado.web.StaticFileHandler, dict(
                path=tornado_settings['static_css']
            )),
            (r"/compresso/fonts/(.*)", tornado.web.StaticFileHandler, dict(
                path=tornado_settings['static_fonts']
            )),
            (r"/compresso/icons/(.*)", tornado.web.StaticFileHandler, dict(
                path=tornado_settings['static_icons']
            )),
            (r"/compresso/img/(.*)", tornado.web.StaticFileHandler, dict(
                path=tornado_settings['static_img']
            )),
            (r"/compresso/js/(.*)", tornado.web.StaticFileHandler, dict(
                path=tornado_settings['static_js']
            )),
            (
                tornado.routing.PathMatches(r"/compresso/ui/(.*)"),
                MainUIRequestHandler,
            ),
        ])

        # Add preview static file handler
        preview_cache_dir = os.path.join(self.config.get_cache_path(), 'preview')
        os.makedirs(preview_cache_dir, exist_ok=True)
        app.add_handlers(r'.*', [
            (r"/compresso/preview/(.*)", tornado.web.StaticFileHandler, dict(
                path=preview_cache_dir
            )),
        ])

        # Add widgets routes
        from compresso.webserver.plugins import DataPanelRequestHandler
        from compresso.webserver.plugins import PluginStaticFileHandler
        from compresso.webserver.plugins import PluginAPIRequestHandler
        app.add_handlers(r'.*', [
            (
                tornado.routing.PathMatches(r"/compresso/panel/[^/]+(/(?!static/|assets$).*)?$"),
                DataPanelRequestHandler
            ),
            (
                tornado.routing.PathMatches(r"/compresso/plugin_api/[^/]+(/(?!static/|assets$).*)?$"),
                PluginAPIRequestHandler
            ),
            (r"/compresso/panel/.*/static/(.*)", PluginStaticFileHandler, dict(
                path=tornado_settings['static_img']
            )),
        ])

        if self.developer:
            self._log("API Docs - Updating...", level="debug")
            try:
                from compresso.webserver.api_v2.schema.swagger import generate_swagger_file
                errors = generate_swagger_file()
                for error in errors:
                    self._log(error, level="warn")
                else:
                    self._log("API Docs - Updated successfully", level="debug")
            except Exception as e:
                self._log("Failed to reload API schema", message2=str(e), level="error")

        # Start the Swagger UI. Automatically generated swagger.json can also
        # be served using a separate Swagger-service.
        from swagger_ui import tornado_api_doc
        tornado_api_doc(
            app,
            config_path=os.path.join(os.path.dirname(__file__), "..", "webserver", "docs", "api_schema_v2.json"),
            url_prefix="/compresso/swagger",
            title="Compresso application API"
        )

        return app
