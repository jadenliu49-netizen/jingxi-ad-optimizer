#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""京喜自营全站营销广告调整 CLI。

子命令：
  pull    拉计划 + SPU/SKU 毛利
  plan    按保本×1.2 算动作和拉黑清单
  apply   执行改目标 / 暂停 / 拉黑（先 dry-run）
  report  出 md + xlsx + 台账
  run     pull + plan + report（可选 apply）
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

DISC = 0.7
FACTOR = 1.2
CAP = 10.0
MIN_ORDERS = 5
MIN_COST = 100.0
BLACK_COST = 100.0
BLACK_ZERO_COST = 20.0
BID_BATCH = 20
PAUSE_BATCH = 10

K_M = "jdr_jx_trade_promise_ord_gross_profit_rate_jx_trade@jx_ads_ord1"
K_GP = "jdr_jx_trade_promise_ord_gross_profit_jx_trade@jx_ads_ord1"
K_C = "jdr_jx_ad_consume_ad_amt_jx_ad_discount@jx_ads_ord1"
K_A = "jdr_jx_trade_deal_ord_ord_amt_jx_trade@jx_ads_ord1"
K_Q = "jdr_jx_trade_deal_ord_parent__ord_dis_qtty_jx_trade@jx_ads_ord1&parent_ord_not_null_str"


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def dump(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)


def window(args):
    end = args.end or (dt.date.today() - dt.timedelta(days=1)).isoformat()
    start = (dt.date.fromisoformat(end) - dt.timedelta(days=args.days - 1)).isoformat()
    return start, end


def pull_margins(c, start, end, erp, plans):
    try:
        d = c.call("ge_ad_drill", start=start, end=end, group=["spu_id"], by_day=True, erp=erp)
        if d.get("rows"):
            return d["rows"], [], "ge_ad_drill"
        print("[warn] ge_ad_drill 返回空，改用指标概况", file=sys.stderr)
    except Exception as e:
        print("[warn] ge_ad_drill 失败，改用指标概况: %s" % str(e)[:120], file=sys.stderr)

    spu, page = [], 1
    while True:
        d = c.call("ge_board_query", board="index", panel="ad_spu", start=start, end=end,
                   filters={"par_degree": "spu_id"}, page=page, page_size=2000)
        got = d.get("rows") or []
        spu.extend(got)
        if len(got) < 2000:
            break
        page += 1

    skus = []
    for p in plans:
        skus.extend(str(s) for s in (p.get("skuIdList") or []))
    skus = list(dict.fromkeys(skus))
    sku_rows = []
    for i in range(0, len(skus), 400):
        chunk = skus[i:i + 400]
        d = c.call("ge_board_query", board="index", panel="ad_sku", start=start, end=end,
                   filters={"par_degree": "sku_id", "sku_id": chunk}, page_size=500)
        sku_rows.extend(d.get("rows") or [])
    return spu, sku_rows, "index"


def norm_spu(r, source):
    if source == "ge_ad_drill":
        return {"spu": str(r.get("spu_id")), "m": f(r.get("裸毛利率")),
                "post": f(r.get("广告投后毛利")), "gmv": f(r.get("广告成交金额")),
                "cost": f(r.get("消耗")), "orders": f(r.get("广告单量"))}
    return {"spu": str(r.get("spu_id")), "m": f(r.get(K_M)),
            "post": f(r.get(K_GP)) - DISC * f(r.get(K_C)),
            "gmv": f(r.get(K_A)), "cost": f(r.get(K_C)), "orders": f(r.get(K_Q))}


def norm_sku(r, source):
    if source == "ge_ad_drill":
        return {"sku": str(r.get("sku_id")), "spu": str(r.get("spu_id")),
                "m": f(r.get("裸毛利率")), "post": f(r.get("广告投后毛利")),
                "cost": f(r.get("消耗")), "orders": f(r.get("广告单量"))}
    return {"sku": str(r.get("sku_id")), "spu": str(r.get("spu_id")), "m": f(r.get(K_M)),
            "post": f(r.get(K_GP)) - DISC * f(r.get(K_C)),
            "cost": f(r.get(K_C)), "orders": f(r.get(K_Q))}


def cmd_pull(args):
    from blacklight import BlacklightClient

    start, end = window(args)
    with BlacklightClient() as c:
        plans = c.call("jzt_swa_ad_all", with_rows=True, start_day=start, end_day=end)
        rows = plans.get("rows") or []
        print("计划 %d 个，窗口 %s ~ %s" % (len(rows), start, end))
        spu, sku, source = pull_margins(c, start, end, args.erp, rows)
    dump(os.path.join(args.out, "plans.json"), {"window": [start, end], "rows": rows})
    dump(os.path.join(args.out, "spu_margin.json"),
         {"source": source, "rows": [norm_spu(x, source) for x in spu]})
    dump(os.path.join(args.out, "sku_margin.json"),
         {"source": source, "rows": [norm_sku(x, source) for x in sku]})
    print("毛利来源 %s：SPU %d 行，SKU %d 行" % (source, len(spu), len(sku)))
    return 0


def cmd_plan(args):
    plans = load(os.path.join(args.data, "plans.json"), {"rows": []})["rows"]
    spu = {x["spu"]: x for x in load(os.path.join(args.data, "spu_margin.json"), {"rows": []})["rows"]}
    sku = {x["sku"]: x for x in load(os.path.join(args.data, "sku_margin.json"), {"rows": []})["rows"]}
    out = []
    for p in plans:
        g = spu.get(str(p.get("spuId"))) or {}
        m = g.get("m")
        t = p.get("出价")
        orders = p.get("全站订单行") or 0
        cost = p.get("花费") or 0
        active = p.get("状态") == "有效"
        be = (DISC / m) if (m and m > 0) else None
        floor = min(CAP, round(be * FACTOR * 2) / 2) if be else None
        action, new = "维持", None
        if not active:
            action = "非有效"
        elif m is None:
            action = "缺毛利"
        elif m <= 0:
            action = "暂停"
        elif be * FACTOR > CAP:
            action = "暂停"
        elif orders < MIN_ORDERS:
            action = "样本不足"
        elif t and floor < t - 0.05:
            action, new = "降目标", floor
        elif t and floor > t + 0.05:
            action, new = "升目标", floor

        bl = []
        for s in (p.get("skuIdList") or []):
            r = sku.get(str(s))
            if not r:
                continue
            if (r["post"] < 0 and r["cost"] >= BLACK_COST) or (
                    r["m"] is not None and r["m"] <= 0 and r["cost"] >= BLACK_ZERO_COST):
                bl.append((str(s), r["post"]))
        bl.sort(key=lambda x: x[1])
        out.append({
            "name": p.get("推广名") or "", "spu": str(p.get("spuId")),
            "gid": str(p.get("groupId")), "cid": str(p.get("campaignId")),
            "status": p.get("状态"), "target": t, "new": new, "action": action,
            "margin": m, "breakeven": be, "orders": orders, "cost": cost,
            "attain": p.get("ROI达成率%"), "gmv": p.get("全站交易额") or 0,
            "skus": [str(s) for s in (p.get("skuIdList") or [])],
            "blacklist": [x[0] for x in bl][:50],
            "blacklist_n": len(bl),
            "blacklist_loss": round(sum(x[1] for x in bl), 2),
        })
    dump(args.out, out)
    from collections import Counter
    print("动作分布", dict(Counter(x["action"] for x in out)))
    return 0


def cmd_apply(args):
    acts = load(args.actions, [])
    todo = [x for x in acts if x["action"] in ("降目标", "升目标") and x.get("new")]
    pause = [x for x in acts if x["action"] == "暂停"]
    black = [x for x in acts if x.get("blacklist") and x["action"] != "暂停"]
    print("待改目标 %d，待暂停 %d，待拉黑 %d" % (len(todo), len(pause), len(black)))
    if args.dry_run:
        for x in todo:
            print("  %s %s -> %s" % (x["name"][:20], x["target"], x["new"]))
        for x in pause:
            print("  暂停 %s" % x["name"][:20])
        return 0

    from blacklight import BlacklightClient

    ok_bid = ok_pause = ok_black = 0
    with BlacklightClient() as c:
        for i in range(0, len(todo), BID_BATCH):
            chunk = todo[i:i + BID_BATCH]
            plan = {x["gid"]: x["new"] for x in chunk}
            try:
                dry = c.call("jzt_swa_bid_dryrun", plan=plan)
                res = c.call("jzt_swa_bid_update", plan=plan, confirm=dry["confirm_token"])
                ok_bid += res.get("成功") or 0
                print("改目标 %d/%d 成功 %s" % (i // BID_BATCH + 1, (len(todo) + 19) // 20, res.get("成功")))
            except Exception as e:
                print("改目标批次失败: %s" % str(e)[:150], file=sys.stderr)
            time.sleep(1.5)

        for i in range(0, len(pause), PAUSE_BATCH):
            ids = [int(x["cid"]) for x in pause[i:i + PAUSE_BATCH]]
            try:
                dry = c.call("jzt_swa_status_dryrun", campaign_ids=ids, operation="stop")
                res = c.call("jzt_swa_status_update", campaign_ids=ids, operation="stop",
                             confirm=dry["confirm_token"])
                ok_pause += res.get("成功") or 0
                print("暂停 %d 个，成功 %s" % (len(ids), res.get("成功")))
            except Exception as e:
                print("暂停失败: %s" % str(e)[:150], file=sys.stderr)
            time.sleep(1.5)

        for x in black:
            add = [int(s) for s in x["blacklist"]]
            token = None
            for attempt in range(3):
                try:
                    dry = c.call("jzt_swa_sku_black_dryrun", campaign_id=int(x["cid"]),
                                 ad_group_id=int(x["gid"]), add=add)
                    token = dry.get("confirm_token")
                except Exception as e:
                    print("拉黑预演失败 %s: %s" % (x["name"][:12], str(e)[:100]), file=sys.stderr)
                if token:
                    break
                time.sleep(65)
            if not token:
                continue
            try:
                res = c.call("jzt_swa_sku_black_update", campaign_id=int(x["cid"]),
                             ad_group_id=int(x["gid"]), add=add, confirm=token)
                if res.get("落地一致"):
                    ok_black += 1
                print("拉黑 %s 新增 %d 一致 %s" % (x["name"][:12], len(res.get("新增") or []), res.get("落地一致")))
            except Exception as e:
                print("拉黑失败 %s: %s" % (x["name"][:12], str(e)[:100]), file=sys.stderr)
            time.sleep(1.5)
    print("完成：改目标 %d，暂停 %d，拉黑 %d" % (ok_bid, ok_pause, ok_black))
    return 0


def cmd_report(args):
    acts = load(args.actions, [])
    plans = load(os.path.join(args.data, "plans.json"), {"rows": []})["rows"]
    os.makedirs(args.out, exist_ok=True)
    today = dt.date.today().isoformat()
    total_cost = sum((p.get("花费") or 0) for p in plans)
    total_gmv = sum((p.get("全站交易额") or 0) for p in plans)
    total_orders = sum((p.get("全站订单行") or 0) for p in plans)
    lower = [x for x in acts if x["action"] == "降目标"]
    raise_ = [x for x in acts if x["action"] == "升目标"]
    pause = [x for x in acts if x["action"] == "暂停"]
    blp = [x for x in acts if x.get("blacklist") and x["action"] != "暂停"]

    md = ["# 广告调整报告 %s" % today, "",
          "- 计划数：%d" % len(plans),
          "- 30 天花费：%.0f 元" % total_cost,
          "- 30 天成交：%.0f 元" % total_gmv,
          "- 30 天订单：%d" % total_orders,
          "- 动作：降目标 %d、升目标 %d、暂停 %d、拉黑计划 %d" % (
              len(lower), len(raise_), len(pause), len(blp)), ""]
    md.append("## 降目标")
    md.append("| 品 | 现目标 | 新目标 | 毛利率 | 保本 | 30天单 | 花费 |")
    md.append("|---|---|---|---|---|---|---|")
    for x in sorted(lower, key=lambda y: -y["cost"])[:50]:
        md.append("| %s | %s | %s | %.1f%% | %.2f | %d | %.0f |" % (
            x["name"][:22], x["target"], x["new"], (x["margin"] or 0) * 100,
            x["breakeven"] or 0, x["orders"], x["cost"]))
    md.append("")
    md.append("## 升目标")
    md.append("| 品 | 现目标 | 新目标 | 毛利率 | 保本 | 30天单 | 花费 |")
    md.append("|---|---|---|---|---|---|---|")
    for x in sorted(raise_, key=lambda y: -y["cost"])[:50]:
        md.append("| %s | %s | %s | %.1f%% | %.2f | %d | %.0f |" % (
            x["name"][:22], x["target"], x["new"], (x["margin"] or 0) * 100,
            x["breakeven"] or 0, x["orders"], x["cost"]))
    md.append("")
    md.append("## 暂停")
    for x in pause:
        md.append("- %s（毛利率 %.1f%%，30天花费 %.0f）" % (
            x["name"][:24], (x["margin"] or 0) * 100, x["cost"]))
    md.append("")
    md.append("## 拉黑 SKU")
    for x in sorted(blp, key=lambda y: y["blacklist_loss"])[:30]:
        md.append("- %s：%d 个，预计少亏 %.0f 元" % (x["name"][:24], len(x["blacklist"]), -x["blacklist_loss"]))
    path = os.path.join(args.out, "广告调整_%s.md" % today)
    open(path, "w", encoding="utf-8").write("\n".join(md))
    print("md", path)

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "计划调整"
        ws.append(["品名", "SPU", "状态", "动作", "现目标", "新目标", "毛利率", "保本ROI",
                   "30天单", "30天花费", "达成率", "拉黑SKU数"])
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="C00000")
        for x in acts:
            ws.append([x["name"], x["spu"], x["status"], x["action"], x["target"], x["new"],
                       x["margin"], x["breakeven"], x["orders"], x["cost"], x["attain"],
                       len(x["blacklist"])])
        for i, w in enumerate([34, 16, 8, 10, 8, 8, 9, 9, 8, 10, 8, 10], 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
        xp = os.path.join(args.out, "广告调整明细_%s.xlsx" % today)
        wb.save(xp)
        print("xlsx", xp)
    except Exception as e:
        print("xlsx 失败: %s" % str(e)[:120], file=sys.stderr)
    return 0


def cmd_run(args):
    args.out_data = args.data
    cmd_pull(args)
    args.out = os.path.join(args.data, "actions.json")
    cmd_plan(args)
    if args.apply:
        cmd_apply(args)
    cmd_report(args)
    return 0


def main():
    ap = argparse.ArgumentParser(description="京喜自营全站营销广告调整")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--erp", default="", help="采销 ERP，默认用 blacklight 当前登录")
        p.add_argument("--days", type=int, default=30)
        p.add_argument("--end", default="")

    p = sub.add_parser("pull")
    common(p)
    p.add_argument("--out", default="data")
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser("plan")
    p.add_argument("--data", default="data")
    p.add_argument("--out", default="data/actions.json")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("apply")
    p.add_argument("--actions", default="data/actions.json")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("report")
    p.add_argument("--data", default="data")
    p.add_argument("--actions", default="data/actions.json")
    p.add_argument("--out", default=".")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("run")
    common(p)
    p.add_argument("--data", default="data")
    p.add_argument("--out", default=".")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_run)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
