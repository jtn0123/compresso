# Compresso API

## Rules regarding endpoint creation:
1. All data will be returned in JSON format.
1. The success status of the data will be returned using HTTP status codes.
    - 200: for all successfully returned data.
    - 400: for errors caused by the client request. (self.STATUS_ERROR_EXTERNAL)
    - 404: for an incorrectly structured API endpoint. (self.STATUS_ERROR_ENDPOINT_NOT_FOUND)
    - 405: for a request to an API endpoint with a disallowed method. (self.STATUS_ERROR_METHOD_NOT_ALLOWED)
    - 500: status for internal errors and exception handling. (self.STATUS_ERROR_INTERNAL)
1. Expected request failures should raise a structured public error:
   ```
    raise BaseApiError(
        "Invalid request",
        messages={"field": ["Required"]},
        private_detail="Diagnostic detail for correlated server logs",
    )
   ```
   The shared base handler owns the status and response body:
   ```
   {
        "error": "400: Invalid request",
        "messages": {"field": ["Required"]},
        "error_id": "opaque-correlation-id"
   }
   ```
1. The returned 'error' message should not be parsed by the client application. This message is subject to change.
1. Endpoint methods may omit local exception handling because the router owns escaped expected and unexpected errors. If cleanup is required, delegate after cleanup:
    ```
    try:
        ...
    except BaseApiError as bae:
        cleanup()
        self.handle_base_api_error(bae)
    except Exception as e:
        cleanup()
        self.handle_unhandled_error(e)
    ```
1. Never return raw request bodies or unexpected exception text to clients. Use correlation IDs to find private diagnostics in server logs.
