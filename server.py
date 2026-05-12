"""author_agent Web 服务 — Flask REST API + 前端管理界面

启动:
    python server.py
    或: start_server.bat

访问:
    http://127.0.0.1:8820

v1.1 修复: 标题提取过滤表头行、JSON解析容错

依赖:
    CDP Proxy (localhost:3456) + Chrome 远程调试
"""
import sys, os, json, time, re, urllib.parse, urllib.request
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory

sys.path.insert(0, str(Path(__file__).parent))
from author_agent import Pipeline, AuthorRecord, extract_from_text
from author_agent.config import OUTPUT_DIR
from author_agent.cdp_client import (
    new_tab, close_tab, navigate, eval_js, click_at, type_text,
    page_text, page_title, wait_for_load, inject_notification,
    open_html_reading, extract_author_bio, search_official_site,
)
from author_agent.cnki_api import search_cnki_api, ensure_cnki_tab

app = Flask(__name__, static_folder="static", static_url_path="/static")
pipeline = Pipeline(mode="claude")
TASK_QUEUE = []; TASK_RESULTS = {}

@app.route("/api/pipeline/status")
def pipeline_status():
    recs = {}
    for name, rec in pipeline.records.items():
        filled = sum(1 for v in rec.fields.values() if v)
        recs[name] = {"fields": {k: v for k, v in rec.fields.items() if v}, "filled": filled, "total": len(rec.fields), "missing": rec.missing_high_priority(), "sources": rec.sources}
    return jsonify({"record_count": len(pipeline.records), "pending_tasks": len(pipeline.extraction_tasks), "records": recs})

@app.route("/api/feed", methods=["POST"])
def feed_text():
    data = request.get_json()
    name, text, source = data.get("name",""), data.get("text",""), data.get("source","")
    if not name or not text: return jsonify({"error": "name and text required"}), 400
    pipeline.feed_text(name, text, source); _save_state()
    return jsonify({"status": "ok", "pending_tasks": len(pipeline.extraction_tasks)})

@app.route("/api/tasks")
def get_tasks(): return jsonify(pipeline.get_pending_tasks())

@app.route("/api/apply", methods=["POST"])
def apply_result():
    data = request.get_json()
    name, fields, source = data.get("name",""), data.get("fields",{}), data.get("source","")
    if not name or not fields: return jsonify({"error": "name and fields required"}), 400
    pipeline.apply_extraction_result(name, fields, source); _save_state()
    return jsonify({"status": "ok", "record_count": len(pipeline.records)})

@app.route("/api/check")
def check_completeness(): return jsonify({"needs_more": pipeline.check_completeness()})

@app.route("/api/record/<name>")
def get_record(name):
    if name not in pipeline.records: return jsonify({"error": "not found"}), 404
    rec = pipeline.records[name]
    return jsonify({"fields": {k:v for k,v in rec.fields.items() if v}, "all_fields": rec.fields, "sources": rec.sources, "missing": rec.missing_high_priority()})

@app.route("/api/record/<name>", methods=["PUT"])
def update_record(name):
    data = request.get_json()
    if name not in pipeline.records: pipeline.records[name] = AuthorRecord(name=name)
    for label, value in data.get("fields", {}).items(): pipeline.records[name].set_field(label, value, data.get("source","manual"))
    _save_state()
    return jsonify({"status": "ok"})

@app.route("/api/batch", methods=["POST"])
def batch_targets():
    data = request.get_json()
    for t in data.get("targets", []):
        if t.get("name") and t["name"] not in pipeline.records: pipeline.records[t["name"]] = AuthorRecord(name=t["name"])
    _save_state()
    return jsonify({"added": len(data.get("targets",[]))})

@app.route("/")
def index(): return send_from_directory("static", "index.html")

@app.route("/static/<path:path>")
def static_files(path): return send_from_directory("static", path)

# Data persistence
STATE_FILE = Path(__file__).parent / "entity_matching2" / "_server_state.json"

def _save_state():
    os.makedirs(STATE_FILE.parent, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"records": {n: r.to_dict() for n,r in pipeline.records.items()}, "sources": {n: r.sources for n,r in pipeline.records.items()}}, f, ensure_ascii=False, indent=2)

def _load_state():
    if not STATE_FILE.exists(): return
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        for name, fields in state.get("records", {}).items():
            rec = AuthorRecord(name=name)
            for label, val in fields.items():
                if val: rec.fields[label] = val
            rec.sources = state.get("sources", {}).get(name, {})
            pipeline.records[name] = rec
    except: pass

@app.route("/api/save", methods=["POST"])
def save_records():
    paths = pipeline.save(); log_path = pipeline.save_log(); _save_state()
    return jsonify({"files": paths, "log": log_path})

# Search API
SEARCH_SESSIONS = {}

@app.route("/api/search/start", methods=["POST"])
def search_start():
    data = request.get_json()
    name = data.get("name", ""); institution = data.get("institution", "")
    if not name: return jsonify({"error": "name required"}), 400
    if name not in pipeline.records: pipeline.records[name] = AuthorRecord(name=name)
    session = {"name": name, "institution": institution, "stage": "cnki_search", "tabs": []}
    tab_id = ensure_cnki_tab()
    if not tab_id: return jsonify({"error": "CDP Proxy not running"}), 503
    session["cnki_tab"] = tab_id; session.setdefault("tabs", []).append(tab_id)

    # Sync XHR search (v1.1: filter table headers from titles)
    js_xhr = 'var cs=window.cnkiSearch;var base=JSON.parse(cs.getSearchJsonInfo());base.QNode.QGroup=[{Key:"S",Title:"",Logic:0,Items:[],ChildItems:[]}];var qg=base.QNode.QGroup[0];qg.ChildItems=[{Key:"a",Title:"",Logic:0,Items:[{Key:"a",Title:"",Logic:0,Field:"AU",Operator:"DEFAULT",Value:"'+name+'",Value2:""}],ChildItems:[]},{Key:"b",Title:"",Logic:0,Items:[{Key:"b",Title:"",Logic:0,Field:"AF",Operator:"FUZZY",Value:"'+institution+'",Value2:""}],ChildItems:[]}];var qj=JSON.stringify(base);var x=new XMLHttpRequest();x.open("POST","/kns8s/brief/grid",false);x.setRequestHeader("Content-Type","application/x-www-form-urlencoded;charset=UTF-8");x.send("boolSearch=true&QueryJson="+encodeURIComponent(qj));window.__h=x.responseText;var m=x.responseText.match(/共找到<\\/span>\\s*<em>(\\d+)<\\/em>/);var titles=[];var tr=/<a[^>]*class="fz14"[^>]*>([^<]+)<\\/a>/g;var tm;while(tm=tr.exec(x.responseText)){var tt=tm[1].trim();if(tt.length>3&&tt!="题名"&&tt!="作者"&&tt!="来源"&&tt!="发表时间"&&tt!="数据库"&&tt!="被引"&&tt!="下载"&&tt!="操作")titles.push(tt)};var hasHtml=x.responseText.indexOf("HTML阅读")>-1;JSON.stringify({count:m?m[1]:"0",len:x.responseText.length,titles:titles,hasHtml:hasHtml})'
    raw = eval_js(tab_id, js_xhr)
    try: result = json.loads(str(raw))
    except: result = {}
    result["resultHtml"] = "stored_in_window"

    if result.get("count") and int(result["count"]) > 0:
        session["stage"] = "results"
        papers = {"count": int(result["count"]), "papers": [{"title": t, "access": "HTML" if result.get("hasHtml") else "download"} for t in result.get("titles", [])[:10]]}
        SEARCH_SESSIONS[name] = session; _save_state()
        return _auto_extract_paper(name, session, result)

    body = page_text(tab_id)
    if "共找到" in body or "条结果" in body:
        session["stage"] = "results"
        SEARCH_SESSIONS[name] = session
        return jsonify({"status": "results", "name": name, "result_count": _parse_cnki_results(tab_id).get("count",0), "papers": _parse_cnki_results(tab_id).get("papers",[])[:10]})

    SEARCH_SESSIONS[name] = session
    return jsonify({"status": "need_prime", "name": name, "message": "知网页面需首次激活,请在Chrome知网页手动搜索一次"})

def _auto_extract_paper(name, session, api_result):
    tab_id = session.get("cnki_tab", ""); institution = session.get("institution", "")
    stages = [{"name":"CNKI搜索","status":"完成","detail":f"找到{api_result.get('count',0)}条结果"}]
    open_count = 0; bios_found = []
    if not tab_id: return _fallback_results(name, api_result)

    # Inject + open HTML (max 5)
    eval_js(tab_id, 'var bb=document.getElementById("briefBox");if(bb){bb.innerHTML=window.__h};"ok"')
    time.sleep(0.5)
    try: html_count = int(eval_js(tab_id, 'var c=0;document.querySelectorAll("a").forEach(function(a){if(a.textContent.indexOf("HTML阅读")>-1)c++});String(c)') or 0)
    except: html_count = 0

    if html_count == 0:
        stages.append({"name":"论文HTML","status":"跳过","detail":"无HTML阅读"})
    else:
        for i in range(min(html_count, 5)):
            eval_js(tab_id, f'var c=0;document.querySelectorAll("a").forEach(function(a){{if(a.textContent.indexOf("HTML阅读")>-1){{c++;if(c=={i+1})a.id="__ht{i+1}"}}}});"m"')
            time.sleep(0.2)
            if click_at(tab_id, f"#__ht{i+1}").get("clicked"): open_count += 1
            time.sleep(2.5)
        stages.append({"name":"论文HTML","status":"完成","detail":f"打开{open_count}篇/{html_count}个"})

        time.sleep(1)
        targets_raw = _get_cdp("targets")
        html_tabs = [t["targetId"] for t in (targets_raw if isinstance(targets_raw, list) else []) if "HTML" in t.get("title","") or "reader" in t.get("url","")]
        for ht in html_tabs[-open_count:]:
            try:
                bio = extract_author_bio(ht)
                if bio and name in bio: bios_found.append(bio); pipeline.feed_text(name, bio, "论文HTML全文_作者简介")
                close_tab(ht)
            except: pass

        if bios_found:
            stages.append({"name":"作者简介","status":"完成","detail":f"{len(bios_found)}篇含目标作者"})
            if name not in pipeline.records: pipeline.records[name] = AuthorRecord(name=name)
            pipeline.records[name].extract_from_text("；".join(bios_found), "论文HTML全文_作者简介")
        else:
            stages.append({"name":"作者简介","status":"跳过","detail":"不含目标作者"})

    # Bing search for official site
    if institution:
        try:
            bing_url = f"https://cn.bing.com/search?q={urllib.parse.quote(f'{name} {institution}')}&mkt=zh-CN"
            web_tab = new_tab(bing_url)
            if web_tab:
                session.setdefault("tabs",[]).append(web_tab); time.sleep(3)
                links_raw = eval_js(web_tab, 'var as=document.querySelectorAll("a");var r=[];as.forEach(function(a){var h=a.href;var t=a.textContent.trim().slice(0,80);if(h&&h.startsWith("http")&&t.length>3)r.push({h:h,t:t})});JSON.stringify(r.slice(0,30))')
                try: all_links = json.loads(str(links_raw))
                except: all_links = []
                edu_links = [l for l in all_links if ".edu.cn" in l.get("h","")]
                target_url = ""
                for l in edu_links:
                    if name in l.get("t",""): target_url = l["h"]; break
                if not target_url and edu_links: target_url = edu_links[0]["h"]
                if target_url:
                    navigate(web_tab, target_url); time.sleep(4)
                    profile_text = page_text(web_tab)
                    if profile_text and len(profile_text) > 200 and name in profile_text:
                        pipeline.feed_text(name, profile_text, "官网个人页")
                        if name not in pipeline.records: pipeline.records[name] = AuthorRecord(name=name)
                        pipeline.records[name].extract_from_text(profile_text, "官网个人页")
                        stages.append({"name":"官网补全","status":"完成","detail":f"从{target_url.split('/')[2]}提取"})
                    else: stages.append({"name":"官网补全","status":"跳过","detail":"不含目标作者"})
                else: stages.append({"name":"官网补全","status":"跳过","detail":"未搜到.edu.cn"})
                close_tab(web_tab)
        except Exception as e: stages.append({"name":"官网补全","status":"跳过","detail":str(e)[:30]})
    else: stages.append({"name":"官网补全","status":"跳过","detail":"无机构信息"})

    if name not in pipeline.records: pipeline.records[name] = AuthorRecord(name=name)
    rec = pipeline.records[name]; cleaned = _clean_fields(rec); _save_state()
    return jsonify({"status":"complete","name":name,"result_count":api_result.get("count",0),"stages":[{"name":"CNKI搜索","status":"完成","detail":f"找到{api_result.get('count',0)}条结果"}]+stages,"fields":{k:v for k,v in rec.fields.items() if v},"cleaned":cleaned,"missing_high_priority":rec.missing_high_priority()})

def _get_cdp(endpoint):
    try:
        with urllib.request.urlopen(f"http://localhost:3456/{endpoint}", timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except: return []

def _clean_fields(rec):
    cleaned = {}
    bd = rec.fields.get("生卒年或个人活动日期", "")
    if bd:
        m = re.match(r'(\d{4})\s*[-–—]\s*(\d{4})?', bd)
        if m:
            y1 = int(m.group(1)); y2 = int(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else None
            if y1 < 1930 or y1 > 2010 or y1 >= 1995 or (y2 and (y2 > 2026 or y2 - y1 > 60)): rec.fields["生卒年或个人活动日期"] = ""
            else: cleaned["生卒年或个人活动日期"] = rec.fields["生卒年或个人活动日期"]
    return cleaned

def _fallback_results(name, api_result):
    return jsonify({"status":"results","name":name,"result_count":api_result.get("count",0)})

def _parse_cnki_results(tab_id):
    body = page_text(tab_id); count = 0
    m = re.search(r'共找到\s*(\d+)\s*条结果', body)
    if m: count = int(m.group(1))
    return {"count": count, "papers": []}

if __name__ == "__main__":
    from waitress import serve
    _load_state(); os.makedirs(str(OUTPUT_DIR), exist_ok=True)
    print(f"\n  author_agent v1.1\n  http://127.0.0.1:8820\n  data: {OUTPUT_DIR}\n  loaded {len(pipeline.records)} records\n")
    serve(app, host="127.0.0.1", port=8820)
