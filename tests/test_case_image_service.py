import base64
import io
import os
from pathlib import Path

import httpx
from PIL import Image

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.llm.config import RouteConfig, RouterConfig
from mathworkstation.llm.image_router import ImageRouter
from mathworkstation.llm.image_service import CaseImageService


def test_case_image_service_registers_valid_image_without_prompt(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    os.environ["CASE_IMAGE_TEST_KEY"] = "fake-image-test-credential"
    config = RouterConfig(
        routes=[
            RouteConfig(
                name="image",
                base_url="https://image.test/v1",
                api_key_env="CASE_IMAGE_TEST_KEY",
                models=["image-test"],
                kind="image",
            )
        ]
    )
    router = ImageRouter(
        config,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [{"b64_json": encoded}]})),
    )
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Image")
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    result = CaseImageService(cases, artifacts, figures, router).generate(
        case["case_id"], "示意图", "private image prompt"
    )
    figure = result["figure"]
    assert figure["status"] == "DRAFT"
    assert "private image prompt" not in str(figure)
    assert len(figure["parameters"]["prompt_sha256"]) == 64
    assert (cases.case_root(case["case_id"]) / figure["path"]).is_file()
    audit = (cases.case_root(case["case_id"]) / ".internal" / "llm_events.jsonl")
    assert audit.is_file()
    assert "private image prompt" not in audit.read_text(encoding="utf-8")
