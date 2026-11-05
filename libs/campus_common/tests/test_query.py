from campus_common.errors import register_error_handlers
from campus_common.query import query_model


def test_query_model_returns_validation_error_for_cross_field_rule():
    from typing import Annotated

    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    from pydantic import BaseModel, model_validator

    class Span(BaseModel):
        start: int
        end: int

        @model_validator(mode="after")
        def _order(self):
            if self.end <= self.start:
                raise ValueError("end 必须大于 start")
            return self

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/spans")
    def spans(span: Annotated[Span, Depends(query_model(Span))], page: int = 1):
        return {"span": span.model_dump(), "page": page}

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/spans", params={"start": 1, "end": 2, "page": 3}).json() == {
        "span": {"start": 1, "end": 2},
        "page": 3,
    }
    reversed_span = client.get("/spans", params={"start": 2, "end": 1})
    assert reversed_span.status_code == 422
    assert reversed_span.json()["code"] == "VALIDATION_ERROR"
    assert reversed_span.json()["details"][0]["loc"] == ["query"]
