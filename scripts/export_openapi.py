"""导出某个服务的 OpenAPI 到标准输出。在服务目录下运行：

cd services/m1-seat && uv run python ../../scripts/export_openapi.py > ../../contracts/openapi/m1-seat.json
"""

import json
import os
import sys

os.environ["APP_VERSION"] = "contract"  # 契约快照不随部署版本变化
sys.path.insert(0, os.getcwd())

from app.main import app  # noqa: E402

json.dump(app.openapi(), sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
sys.stdout.write("\n")
