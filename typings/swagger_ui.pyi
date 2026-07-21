from tornado.web import Application

def tornado_api_doc(
    app: Application,
    *,
    config_path: str,
    url_prefix: str,
    title: str,
) -> None: ...
