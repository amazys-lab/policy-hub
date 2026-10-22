# -*- coding: utf-8 -*-
"""清单 Excel 导出接口（服务端生成，浏览器直接下载）。

为什么要有这个出口
------------------
系统原本只能看不能出。中介的核心交付物就是「一份清单 Excel」—— 没有这个出口，
顾问给客户发东西还得自己复制粘贴，系统等于只进不出。

**复用而非重写**：列定义与渲染全部来自 `pipeline/export_excel.py`
（`C_COLS` / `C_CENTER_COLS` / `build_c_rows` / `write_sheet` / `build_city_overview`）。
这里只做「取数 → 组装工作簿 → 返回二进制」三件事。
★ 绝不在这里复制第二份列定义 —— 一复制就分叉，成品和线上两张表从此对不上
（`tests/test_c_excel_form.py` 守的就是这件事）。
"""
import io
import os
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PIPE = os.path.join(ROOT, "pipeline")
if _PIPE not in sys.path:
    sys.path.insert(0, _PIPE)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

router = APIRouter(prefix="/api/v1", tags=["导出"])


class ExportIn(BaseModel):
    profile: Dict[str, Any] = {}
    title: Optional[str] = None


def _city_name(code: str) -> str:
    try:
        import mappers as M
        return M.city(code) or code
    except Exception:
        return code or "全部城市"


def _build_workbook(records: List[Dict[str, Any]], title: str) -> bytes:
    """组装 C 端口径工作簿：Sheet1 政策总表 + Sheet2 按城市速览。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment
    import export_excel as X                       # 函数内 import：其顶层有 I/O

    wb = Workbook()
    ws = wb.active
    ws.title = "政策总表"
    X.write_sheet(ws, X.build_c_rows(records), cols=X.C_COLS,
                  center=X.C_CENTER_COLS, freeze="E2")

    ov = X.build_city_overview(records)
    ws2 = wb.create_sheet("按城市速览")
    ws2.append(["城市", "政策条数", "补贴类别分布", "编号区间"])
    for c in ws2[1]:
        c.fill, c.font = X.HEAD_FILL, X.HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")
    for r in ov:
        ws2.append(r)
    ws2.append([])
    ws2.append(["合计", len(records), "%d 个城市" % len(ov), ""])
    ws2.append([])
    ws2.append(["怎么用", "切到「政策总表」，点「城市」列的筛选箭头可只看该城；"
                          "「办理入口」「政策原文链接」两列可直接点击，也可复制到浏览器。", "", ""])
    for col, w in (("A", 14), ("B", 12), ("C", 52), ("D", 12)):
        ws2.column_dimensions[col].width = w

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _resp(content: bytes, name: str) -> Response:
    # 中文文件名必须走 RFC 5987，否则浏览器会把它当 latin-1 解码成乱码
    return Response(
        content=content,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename*=UTF-8''%s.xlsx" % quote(name)},
    )


@router.post("/export/checklist", summary="按画像导出可申报清单 Excel")
def export_checklist(body: ExportIn):
    """输入画像，导出「这个人/这家企业能申报哪些政策」的 Excel。

    profile 结构与 `/api/v1/match` 完全一致（city 必填）；导出内容为该画像
    匹配到的**全部**政策（不只是首批展示的若干条）。
    """
    from server.app import POL, run_match

    prof = dict(body.profile or {})
    city = (prof.get("city") or "").strip().upper()
    if not city:
        raise HTTPException(400, "profile.city 必填（如 SZ / FZ / GZ）")
    prof["city"] = city

    r = run_match(prof)
    ids: List[str] = []
    for v in (r.get("summary") or {}).values():
        if isinstance(v, list):
            ids.extend([i for i in v if isinstance(i, str)])
    seen, records = set(), []
    for i in ids:
        if i in seen or i not in POL:
            continue
        seen.add(i)
        records.append(POL[i])
    if not records:
        raise HTTPException(404, "该画像没有匹配到政策，无可导出内容（换个城市或调整画像条件再试）")

    title = body.title or "%s可申报政策清单" % _city_name(city)
    return _resp(_build_workbook(records, title), title)


@router.get("/export/city", summary="按城市导出政策清单 Excel")
def export_city(city: str = Query(..., description="城市码，如 SZ / FZ / GZ"),
                domain: str = Query("", description="可选的域过滤")):
    """导出某城市（可限定域）的全部现行有效政策清单。"""
    from server.app import POL, _city_of

    c = (city or "").strip().upper()
    if not c:
        raise HTTPException(400, "city 必填")
    records = [p for p in POL.values()
               if _city_of(p) == c
               and (p.get("valid") or "active") == "active"
               and (not domain or p.get("domain") == domain)]
    if not records:
        raise HTTPException(404, "该城市没有符合条件的政策（检查城市码或域）")

    title = "%s政策清单" % _city_name(c)
    return _resp(_build_workbook(records, title), title)
