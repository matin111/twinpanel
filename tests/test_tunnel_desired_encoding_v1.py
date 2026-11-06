"""Guard the sync tunnel Agent desired-state response serialization contract."""
from __future__ import annotations
import ast
import asyncio
from datetime import datetime
from pathlib import Path
import unittest

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.routing import serialize_response

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"backend/app/routers/tunnels.py"


class DesiredStateEncodingTests(unittest.IsolatedAsyncioTestCase):
    def test_desired_response_is_encoded_on_worker_before_return(self):
        tree=ast.parse(SOURCE.read_text(encoding="utf-8"))
        fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
                and x.name=="desired_tunnels")
        self.assertIsInstance(fn,ast.FunctionDef)  # not async
        result=fn.body[-1]
        self.assertIsInstance(result,ast.Return)
        self.assertEqual(ast.unparse(result.value),
                         "JSONResponse(content=jsonable_encoder(output))")
        calls=[x for x in ast.walk(fn) if isinstance(x,ast.Call)]
        self.assertTrue(any(isinstance(x.func,ast.Attribute) and
                            x.func.attr=="commit" for x in calls))
        src=SOURCE.read_text(encoding="utf-8")
        self.assertIn("from fastapi.responses import JSONResponse",src)
        self.assertIn("from fastapi.encoders import jsonable_encoder",src)

    async def test_wire_format_matches_prior_fastapi_encoding(self):
        # The route still exposes the exact original list/dict structure and
        # the FastAPI encoder's handling of dates and nullable fields.
        payload=[{"id":30,"active_transport":"tp27_fast",
                  "service_routes":[{"protocol":"cisco","port":20007,
                                     "started_at":datetime(2026,11,6,18,0,0),
                                     "config":None},
                                    {"protocol":"v2ray","target_port":9444}],
                  "route_selected":True},
                 {"id":32,"service_routes":[],"route_selected":False}]
        expected=await serialize_response(
            field=None,response_content=payload,
            include=None,exclude=None,by_alias=True,exclude_unset=False,
            exclude_defaults=False,exclude_none=False,is_coroutine=True,
        )
        route_response=JSONResponse(content=jsonable_encoder(payload))
        old_response=JSONResponse(content=expected)
        self.assertEqual(route_response.body,old_response.body)
        self.assertEqual(route_response.media_type,"application/json")


if __name__=="__main__":
    unittest.main()
