from pydantic import BaseModel
from pytest import mark, raises

from xuemian_ai.core.responses import ApiResponse, PageResponse, page_response, success_response
from xuemian_ai.core.status_codes import ApiStatusCode


class Item(BaseModel):
    id: int


@mark.parametrize("status", [ApiStatusCode.OK, ApiStatusCode.CREATED, ApiStatusCode.ACCEPTED])
def test_success_response_uses_numeric_http_status_code(status: ApiStatusCode) -> None:
    response = success_response(Item(id=1), message="创建成功", code=status)

    assert response.model_dump() == {
        "code": status.value,
        "message": "创建成功",
        "data": {"id": 1},
    }


def test_success_response_rejects_error_status() -> None:
    with raises(ValueError, match="200, 201 or 202"):
        success_response(None, code=ApiStatusCode.BAD_REQUEST)


def test_page_response_calculates_total_pages() -> None:
    response = page_response([Item(id=1)], page=2, page_size=20, total=21)

    assert response.model_dump() == {
        "code": 200,
        "message": "查询成功",
        "data": [{"id": 1}],
        "meta": {
            "page": 2,
            "page_size": 20,
            "total": 21,
            "total_pages": 2,
        },
    }


def test_page_response_rejects_invalid_page_size_before_calculation() -> None:
    with raises(ValueError, match="page_size"):
        page_response([], page=1, page_size=0, total=0)


def test_generic_response_models_expose_typed_data_schema() -> None:
    success_schema = ApiResponse[Item].model_json_schema()
    page_schema = PageResponse[Item].model_json_schema()

    assert success_schema["properties"]["data"]["$ref"].endswith("/$defs/Item")
    assert page_schema["properties"]["data"]["items"]["$ref"].endswith("/$defs/Item")
