import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.openapi_contract import (
    ContractDriftError,
    ContractGenerationError,
    check_contract,
    render_contract,
    write_contract,
)


@pytest.mark.unittest
def test_generation_errors_do_not_replace_the_existing_contract(tmp_path):
    output_path = tmp_path / "api_schema_v2.json"
    output_path.write_bytes(b"existing contract")

    with (
        patch(
            "scripts.openapi_contract.generate_swagger_file",
            return_value=["API Docs - undocumented route"],
        ),
        pytest.raises(ContractGenerationError, match="undocumented route"),
    ):
        write_contract(output_path)

    assert output_path.read_bytes() == b"existing contract"


@pytest.mark.unittest
def test_check_reports_contract_drift_without_modifying_the_file(tmp_path):
    output_path = tmp_path / "api_schema_v2.json"
    output_path.write_bytes(b"existing contract")

    def generate_new_contract(generated_path: str | Path) -> list[str]:
        Path(generated_path).write_bytes(b"new contract")
        return []

    with (
        patch(
            "scripts.openapi_contract.generate_swagger_file",
            side_effect=generate_new_contract,
        ),
        pytest.raises(ContractDriftError, match="contract drift"),
    ):
        check_contract(output_path)

    assert output_path.read_bytes() == b"existing contract"


@pytest.mark.unittest
def test_file_info_contract_uses_typed_nested_media_schemas():
    contract = json.loads(render_contract())
    schemas = contract["components"]["schemas"]
    properties = schemas["FileInfoResponse"]["properties"]

    assert properties["video_streams"]["items"]["$ref"].endswith("/VideoStream")
    assert properties["audio_streams"]["items"]["$ref"].endswith("/AudioStream")
    assert properties["subtitle_streams"]["items"]["$ref"].endswith("/SubtitleStream")
    assert properties["format"]["$ref"].endswith("/FormatInfo")
