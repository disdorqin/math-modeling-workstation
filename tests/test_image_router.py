import base64
import os

import httpx

from mathworkstation.llm.config import RouteConfig, RouterConfig
from mathworkstation.llm.image_router import ImageRequest, ImageRouter


def test_image_router_decodes_base64_without_logging_prompt() -> None:
    os.environ["TEST_IMAGE_KEY"] = "fake-image-credential"
    config = RouterConfig(
        routes=[
            RouteConfig(
                name="image",
                base_url="https://image.test/v1",
                api_key_env="TEST_IMAGE_KEY",
                models=["gpt-image-test"],
                kind="image",
            )
        ]
    )
    expected = b"fake-png-bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(expected).decode("ascii")}]},
        )

    result = ImageRouter(config, transport=httpx.MockTransport(handler)).generate(
        ImageRequest("private prompt")
    )
    assert result.content == expected
    assert result.route_name == "image"
