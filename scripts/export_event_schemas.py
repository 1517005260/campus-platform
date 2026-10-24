"""导出跨模块消息的 JSON Schema（contracts/events/schemas.json），供 asyncapi.yaml 引用。"""

import json
import sys

from campus_common.events import EVENT_TYPES, Envelope

schemas = {"Envelope": Envelope.model_json_schema()}
schemas |= {t: m.model_json_schema() for t, m in sorted(EVENT_TYPES.items())}
json.dump(schemas, sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
sys.stdout.write("\n")
