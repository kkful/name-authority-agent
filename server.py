"""author_agent Web 服务 — Flask REST API + 前端管理界面

启动:
    python server.py
    或: start_server.bat

访问:
    http://127.0.0.1:8820

API 端点:
    POST /api/search/start    — 启动搜捕（知网API+论文HTML+官网）
    GET  /api/pipeline/status — 流水线状态
    POST /api/save            — 保存Excel
    GET  /api/record/<name>   — 查看记录
    PUT  /api/record/<name>   — 更新记录字段

依赖:
    CDP Proxy (localhost:3456) + Chrome 远程调试
    知网标签页需手动激活一次（作者发文检索→任意搜索）
"""
import sys
import os
import json
import time
import re
import urllib.parse
import urllib.request
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
TASK_QUEUE = []  # 待提取任务
TASK_RESULTS = {}  # 已完成提取结果


# ── API ──

@app.route("/api/pipeline/status")
def pipeline_status():
    recs = {}
    for name, rec in pipeline.records.items():
        filled = sum(1 for v in rec.fields.values() if v)
        total = len(rec.fields)
        missing = rec.missing_high_priority()
        recs[name] = {
            "fields": {k: v for k, v in rec.fields.items() if v},
            "filled": filled,
            "total": total,
            "missing": missing,
            "sources": rec.sources,
        }
    return jsonify({
        "record_count": len(pipeline.records),
        "pending_tasks": len(pipeline.extraction_tasks),
        "records": recs,
    })


@app.route("/api/feed", methods=["POST"])
def feed_text():
    data = request.get_json()
    name = data.get("name", "")
    text = data.get("text", "")
    source = data.get("source", "")

    if not name or not text:
        return jsonify({"error": "name and text required"}), 400

    pipeline.feed_text(name, text, source)
    _save_state()
    return jsonify({"status": "ok", "pending_tasks": len(pipeline.extraction_tasks)})


@app.route("/api/tasks")
def get_tasks():
    return jsonify(pipeline.get_pending_tasks())


@app.route("/api/apply", methods=["POST"])
def apply_result():
    data = request.get_json()
    name = data.get("name", "")
    fields = data.get("fields", {})
    source = data.get("source", "")

    if not name or not fields:
        return jsonify({"error": "name and fields required"}), 400

    pipeline.apply_extraction_result(name, fields, source)
    _save_state()
    return jsonify({"status": "ok", "record_count": len(pipeline.records)})


@app.route("/api/check")
def check_completeness():
    needs = pipeline.check_completeness()
    return jsonify({"needs_more": needs})


@app.route("/api/record/<name>")
def get_record(name):
    if name not in pipeline.records:
        return jsonify({"error": "not found"}), 404
    rec = pipeline.records[name]
    return jsonify({
        "fields": {k: v for k, v in rec.fields.items() if v},
        "all_fields": rec.fields,
        "sources": rec.sources,
        "missing": rec.missing_high_priority(),
    })


@app.route("/api/record/<name>", methods=["PUT"])
def update_record(name):
    data = request.get_json()
    if name not in pipeline.records:
        pipeline.records[name] = AuthorRecord(name=name)
    source = data.get("source", "manual")
    for label, value in data.get("fields", {}).items():
        pipeline.records[name].set_field(label, value, source)
    _save_state()
    return jsonify({"status": "ok"})


@app.route("/api/dedup/fields")
def dedup_fields():
    """返回 dedup-librecord 的字段列表"""
    from author_agent.schema import FIELDS
    return jsonify([
        {"label": label, "priority": priority, "hint": hint}
        for _, label, priority, hint in FIELDS
    ])


@app.route("/api/batch", methods=["POST"])
def batch_targets():
    """批量添加搜捕目标"""
    data = request.get_json()
    targets = data.get("targets", [])
    for t in targets:
        name = t.get("name", "")
        if name and name not in pipeline.records:
            pipeline.records[name] = AuthorRecord(name=name)
    _save_state()
    return jsonify({"added": len(targets)})


# ── 前端 ──

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


# ── 数据持久化 ──

STATE_FILE = Path(__file__).parent / "entity_matching2" / "_server_state.json"

def _save_state():
    """保存 pipeline 状态到磁盘"""
    os.makedirs(STATE_FILE.parent, exist_ok=True)
    state = {
        "records": {name: rec.to_dict() for name, rec in pipeline.records.items()},
        "sources": {name: rec.sources for name, rec in pipeline.records.items()},
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def _load_state():
    """从磁盘恢复 pipeline 状态"""
    if not STATE_FILE.exists():
        return
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        for name, fields in state.get("records", {}).items():
            rec = AuthorRecord(name=name)
            for label, val in fields.items():
                if val:
                    rec.fields[label] = val
            sources = state.get("sources", {}).get(name, {})
            rec.sources = sources
            pipeline.records[name] = rec
    except Exception:
        pass

@app.route("/api/save", methods=["POST"])
def save_records():
    paths = pipeline.save()
    log_path = pipeline.save_log()
    _save_state()
    return jsonify({"files": paths, "log": log_path})


# ── 智能体搜捕 API ──

SEARCH_SESSIONS = {}  # name -> {target_id, stage, ...}


@app.route("/api/search/start", methods=["POST"])
def search_start():
    """启动对一位作者的完整搜捕流程"""
    data = request.get_json()
    name = data.get("name", "")
    institution = data.get("institution", "")

    if not name:
        return jsonify({"error": "name required"}), 400

    # 确保记录存在
    if name not in pipeline.records:
        pipeline.records[name] = AuthorRecord(name=name)

    session = {"name": name, "institution": institution, "stage": "cnki_search", "tabs": []}

    # 找或创建知网 tab
    tab_id = ensure_cnki_tab()
    if not tab_id:
        return jsonify({"error": "CDP Proxy 未运行"}), 503

    session["cnki_tab"] = tab_id
    if tab_id not in session["tabs"]:
        session["tabs"].append(tab_id)

    # 同步XHR搜索（存window.__h，供后续DOM注入）
    js_xhr = 'var cs=window.cnkiSearch;var base=JSON.parse(cs.getSearchJsonInfo());base.QNode.QGroup=[{Key:"S",Title:"",Logic:0,Items:[],ChildItems:[]}];var qg=base.QNode.QGroup[0];qg.ChildItems=[{Key:"a",Title:"",Logic:0,Items:[{Key:"a",Title:"",Logic:0,Field:"AU",Operator:"DEFAULT",Value:"'+name+'",Value2:""}],ChildItems:[]},{Key:"b",Title:"",Logic:0,Items:[{Key:"b",Title:"",Logic:0,Field:"AF",Operator:"FUZZY",Value:"'+institution+'",Value2:""}],ChildItems:[]}];var qj=JSON.stringify(base);var x=new XMLHttpRequest();x.open("POST","/kns8s/brief/grid",false);x.setRequestHeader("Content-Type","application/x-www-form-urlencoded;charset=UTF-8");x.send("boolSearch=true&QueryJson="+encodeURIComponent(qj));window.__h=x.responseText;var m=x.responseText.match(/共找到<\\/span>\\s*<em>(\\d+)<\\/em>/);JSON.stringify({count:m?m[1]:"0",len:x.responseText.length})'
    raw = eval_js(tab_id, js_xhr)
    try:
        result = json.loads(str(raw))
    except:
        result = {}
    result["resultHtml"] = "stored_in_window"

    if result.get("count") and int(result["count"]) > 0:
        session["stage"] = "results"
        session["result_html"] = result.get("resultHtml", "")
        papers = {
            "count": int(result["count"]),
            "papers": [
                {"title": t, "access": "HTML" if result.get("hasHtml") else ("原版" if result.get("hasYuanban") else "下载")}
                for t in result.get("titles", [])[:10]
            ]
        }
        SEARCH_SESSIONS[name] = session
        _save_state()

        # 自动链：从API结果HTML中提取论文链接，打开HTML阅读提取作者简介
        return _auto_extract_paper(name, session, result)

    # API搜索失败 → 可能需要激活（Classid为空）
    body = page_text(tab_id)
    if "共找到" in body or "条结果" in body:
        # 用户在页面上手动搜了
        session["stage"] = "results"
        papers = _parse_cnki_results(tab_id)
        SEARCH_SESSIONS[name] = session
        return jsonify({
            "status": "results",
            "name": name,
            "result_count": papers.get("count", 0),
            "papers": papers.get("papers", [])[:10],
        })

    # 需要首次激活：提示用户在浏览器中手动搜索一次
    inject_notification(tab_id,
        f"首次使用需要激活页面：\n请在下方「作者发文检索」填入任意搜索条件 → 点检索\n\n之后所有搜捕全自动，无需重复此操作。")
    SEARCH_SESSIONS[name] = session
    return jsonify({
        "status": "need_prime",
        "name": name,
        "message": f"知网页面需要首次激活。请在Chrome中找到知网标签页，切到「作者发文检索」，填入任意检索条件点搜索。完成后在界面重新添加。"
    })


@app.route("/api/search/continue/<name>", methods=["POST"])
def search_continue(name):
    """用户完成手动操作后，继续自动化：提取结果"""
    session = SEARCH_SESSIONS.get(name)
    if not session:
        return jsonify({"error": "no session"}), 404

    tab_id = session.get("cnki_tab", "")
    if not tab_id:
        return jsonify({"error": "tab lost"}), 500

    body = page_text(tab_id)
    if "共找到" in body:
        session["stage"] = "results"
        papers = _parse_cnki_results(tab_id)
        SEARCH_SESSIONS[name] = session
        return jsonify({
            "status": "results",
            "name": name,
            "result_count": papers.get("count", 0),
            "papers": papers.get("papers", [])[:10],
        })

    return jsonify({"status": "not_ready", "message": "搜索结果页面未就绪，请确认已完成检索"})


@app.route("/api/search/auto_chain/<name>", methods=["POST"])
def search_auto_chain(name):
    """一键到底：搜捕后自动 web 搜官网 + 规则提取 + 喂入 + 保存"""
    session = SEARCH_SESSIONS.get(name)
    if not session:
        return jsonify({"error": "no session"}), 404

    institution = session.get("institution", "")
    results = {"steps": [], "fields": {}}

    # 1. 基础字段
    if name not in pipeline.records:
        pipeline.records[name] = AuthorRecord(name=name)
    rec = pipeline.records[name]
    if institution:
        rec.set_field("在职单位", institution, "搜索条件")

    # 2. CDP 搜百度找官网
    query = f"{name} {institution} 个人主页"
    search_url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}"
    search_tab = new_tab(search_url)
    if search_tab:
        session.setdefault("tabs", []).append(search_tab)
        time.sleep(3)
        links_raw = eval_js(search_tab, """
var as=document.querySelectorAll('a');var r=[];
as.forEach(function(a){var h=a.href;if(h&&h.startsWith('http')&&h.indexOf('baidu.com')===-1)r.push(h)});
JSON.stringify(r.slice(0,20));
""")
        try:
            all_urls = json.loads(str(links_raw))
        except Exception:
            all_urls = []

        edu_url = ""
        for u in all_urls:
            if ".edu.cn" in u and (name in u or institution[:2] in u):
                edu_url = u
                break
        if not edu_url:
            for u in all_urls:
                if ".edu.cn" in u or "baike.baidu.com" in u:
                    edu_url = u
                    break

        if edu_url:
            navigate(search_tab, edu_url)
            time.sleep(3)
            profile_text = page_text(search_tab)
            if profile_text and len(profile_text) > 200 and name in profile_text:
                results["steps"].append("profile_fetched")
                rec.extract_from_text(profile_text, "官网个人页")
                if "男" in profile_text[:1000]:
                    rec.set_field("性别", "男", "官网个人页")
                elif "女" in profile_text[:1000]:
                    rec.set_field("性别", "女", "官网个人页")
                results["steps"].append("extracted")

        close_tab(search_tab)

    # 3. 结果
    results["fields"] = {k: v for k, v in rec.fields.items() if v}
    results["steps"].append("done")

    # 2. 保存
    _save_state()
    pipeline.save()
    pipeline.save_log()
    results["steps"].append("saved")
    results["status"] = "complete"

    return jsonify(results)


@app.route("/api/search/open_html/<name>", methods=["POST"])
def search_open_html(name):
    """点击第一篇论文的 HTML阅读，提取作者简介"""
    session = SEARCH_SESSIONS.get(name)
    if not session:
        return jsonify({"error": "no session"}), 404

    tab_id = session.get("cnki_tab", "")
    html_tab = open_html_reading(tab_id)

    if not html_tab:
        return jsonify({"error": "未找到 HTML阅读 入口，请手动点击"}), 500

    session["html_tab"] = html_tab
    session["tabs"].append(html_tab)
    session["stage"] = "reading"

    bio = extract_author_bio(html_tab)
    SEARCH_SESSIONS[name] = session

    return jsonify({
        "status": "extracted",
        "name": name,
        "bio": bio,
        "next": "LLM 提取结构化字段"
    })


@app.route("/api/search/extract_bio/<name>", methods=["POST"])
def search_extract_bio(name):
    """对已提取的 bio 文本做结构化提取，喂入 pipeline"""
    session = SEARCH_SESSIONS.get(name)
    if not session:
        return jsonify({"error": "no session"}), 404

    data = request.get_json()
    bio_text = data.get("bio", "")
    source = data.get("source", "论文HTML全文_作者简介")

    if bio_text:
        pipeline.feed_text(name, bio_text, source)

    # 也提取 HTML 页面上的完整文本
    html_tab = session.get("html_tab", "")
    if html_tab:
        full_text = page_text(html_tab)
        if full_text and len(full_text) > len(bio_text):
            pipeline.feed_text(name, full_text[:5000], source)

    _save_state()

    # 生成 LLM 提取 prompt
    tasks = pipeline.get_pending_tasks()
    prompt = ""
    for t in tasks:
        if t["name"] == name:
            prompt = t["prompt"]
            break

    return jsonify({
        "status": "fed",
        "name": name,
        "pending_tasks": len(tasks),
        "extraction_prompt": prompt,
    })


@app.route("/api/search/session/<name>")
def search_session(name):
    """查询搜索会话状态"""
    session = SEARCH_SESSIONS.get(name)
    if not session:
        return jsonify({"status": "none"})
    return jsonify({
        "name": session.get("name"),
        "stage": session.get("stage", "unknown"),
        "tabs_count": len(session.get("tabs", [])),
    })


@app.route("/api/search/cleanup/<name>", methods=["POST"])
def search_cleanup(name):
    """清理搜索会话，关闭 tab"""
    session = SEARCH_SESSIONS.pop(name, {})
    for tab_id in session.get("tabs", []):
        try:
            close_tab(tab_id)
        except Exception:
            pass
    return jsonify({"status": "cleaned"})


# ── 知网辅助函数 ──

CNKI_ADV_SEARCH = "https://kns.cnki.net/kns8s/AdvSearch"


def _try_fill_cnki_form(tab_id: str, author: str, institution: str) -> dict:
    """切换标签 + 尝试用值填充 + 通知用户手动完成（React受控表单无法完全自动化）"""
    # 1. 切换到"作者发文检索"标签
    eval_js(tab_id, """
var tabs = document.querySelectorAll('li');
tabs.forEach(function(li) {
    if(li.textContent.indexOf('作者发文检索') > -1) li.click();
});
""")
    time.sleep(1.5)

    # 2. 用原生 setter + InputEvent 设值（尽力而为，React 可能仍不认）
    eval_js(tab_id, f"""
var box=document.querySelectorAll('.input-box');
var ai=box[0]?.querySelector('input[type=text]');
var ii=box[1]?.querySelector('input[type=text]');
var ns=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
function setVal(el,val) {{
    el.focus(); ns.call(el,val);
    el.dispatchEvent(new InputEvent('input',{{bubbles:true,inputType:'insertText',data:val}}));
    el.dispatchEvent(new Event('change',{{bubbles:true}}));
}}
if(ai) setVal(ai,'{author}');
if(ii) setVal(ii,'{institution}');
JSON.stringify({{v1:ai?.value||'',v2:ii?.value||''}});
""")

    # 3. 检查是否已经搜索过了
    body = page_text(tab_id)
    if "共找到" in body or "条结果" in body:
        return {"success": True, "searched": True}

    # 4. 通知用户手动填表单（字段已尽量预填）
    return {"success": True, "searched": False, "needs_manual_input": True}


def _auto_extract_paper(name: str, session: dict, api_result: dict) -> dict:
    """搜索→注入DOM→逐篇打开HTML→提取作者简介→清洗→返回"""
    tab_id = session.get("cnki_tab", "")
    institution = session.get("institution", "")
    import re as _re

    stages = [{"name":"CNKI搜索","status":"完成","detail":f"找到{api_result.get('count',0)}条结果"}]
    open_count = 0
    bios_found = []

    if not tab_id:
        return _fallback_results(name, api_result)

    # ===== 阶段1：注入结果+逐篇打开HTML（最多5篇）=====
    js_inject = 'var bb=document.getElementById("briefBox");if(bb){bb.innerHTML=window.__h};String(document.querySelectorAll("a").length)'
    eval_js(tab_id, js_inject)
    time.sleep(0.5)

    html_count = 0
    try:
        r = eval_js(tab_id, 'var c=0;document.querySelectorAll("a").forEach(function(a){if(a.textContent.indexOf("HTML阅读")>-1)c++});String(c)')
        html_count = int(r) if r and str(r).isdigit() else 0
    except:
        pass

    if html_count == 0:
        stages.append({"name":"论文HTML","status":"跳过","detail":"无HTML阅读入口"})
    else:
        max_open = min(html_count, 5)
        for i in range(max_open):
            idx = i + 1
            # Mark and click
            eval_js(tab_id, f'var c=0;document.querySelectorAll("a").forEach(function(a){{if(a.textContent.indexOf("HTML阅读")>-1){{c++;if(c=={idx})a.id="__ht{idx}"}}}});"m"')
            time.sleep(0.2)
            cr = click_at(tab_id, f"#__ht{idx}")
            if cr.get("clicked"):
                open_count += 1
            time.sleep(2.5)
        stages.append({"name":"论文HTML","status":"完成","detail":f"打开{open_count}篇/{html_count}个入口"})

        # ===== 阶段2：提取每篇的作者简介 =====
        time.sleep(1)
        targets_raw = _get_cdp("targets")
        html_tabs = []
        if isinstance(targets_raw, list):
            for t in targets_raw:
                if "HTML" in t.get("title","") or "reader" in t.get("url",""):
                    html_tabs.append(t["targetId"])

        for ht in html_tabs[-open_count:]:
            try:
                bio = extract_author_bio(ht)
                if bio and name in bio:
                    bios_found.append(bio)
                    pipeline.feed_text(name, bio, "论文HTML全文_作者简介")
                close_tab(ht)
            except:
                pass

        if bios_found:
            stages.append({"name":"作者简介提取","status":"完成","detail":f"{len(bios_found)}篇含目标作者"})
            if name not in pipeline.records:
                pipeline.records[name] = AuthorRecord(name=name)
            # 合并所有bios提取（多篇互补）
            merged_bio = "；".join(bios_found)
            pipeline.records[name].extract_from_text(merged_bio, "论文HTML全文_作者简介")
        else:
            stages.append({"name":"作者简介提取","status":"跳过","detail":"所有论文简介均不含目标作者"})

    # ===== 阶段3：必应搜官网补全 =====
    web_done = False
    if institution:
        try:
            query = f"{name} {institution}"
            bing_url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}&mkt=zh-CN"
            web_tab = new_tab(bing_url)
            if web_tab:
                session.setdefault("tabs", []).append(web_tab)
                time.sleep(3)
                # 提取所有外部链接
                links_raw = eval_js(web_tab, """
var as=document.querySelectorAll('a');var r=[];
as.forEach(function(a){var h=a.href;var t=a.textContent.replace(/\\s+/g,' ').trim().slice(0,80);
if(h&&h.startsWith('http')&&t.length>3)r.push({h:h,t:t});});
JSON.stringify(r.slice(0,30));
""")
                try:
                    all_links = json.loads(str(links_raw))
                except Exception:
                    all_links = []

                # 找edu链接：优先匹配含作者名的
                edu_links = [l for l in all_links if ".edu.cn" in l.get("h","")]
                target_url = ""
                for l in edu_links:
                    if name in l.get("t",""):
                        target_url = l["h"]; break
                if not target_url and edu_links:
                    target_url = edu_links[0]["h"]

                if target_url:
                    navigate(web_tab, target_url)
                    time.sleep(4)
                    profile_text = page_text(web_tab)
                    if profile_text and len(profile_text) > 200 and name in profile_text:
                        web_done = True
                        pipeline.feed_text(name, profile_text, "官网个人页")
                        if name not in pipeline.records:
                            pipeline.records[name] = AuthorRecord(name=name)
                        pipeline.records[name].extract_from_text(profile_text, "官网个人页")
                        stages.append({"name":"官网补全","status":"完成","detail":f"已从{target_url.split('/')[2]}提取字段"})
                    else:
                        stages.append({"name":"官网补全","status":"跳过","detail":"页面不含目标作者"})
                else:
                    stages.append({"name":"官网补全","status":"跳过","detail":"未搜到官网链接"})
                close_tab(web_tab)
        except Exception as e:
            stages.append({"name":"官网补全","status":"跳过","detail":f"搜索失败:{str(e)[:30]}"})
    else:
        stages.append({"name":"官网补全","status":"跳过","detail":"无机构信息"})

    # ===== 汇总清洗 =====
    if name not in pipeline.records:
        pipeline.records[name] = AuthorRecord(name=name)
    rec = pipeline.records[name]
    cleaned = _clean_fields(rec)
    _save_state()

    return jsonify({
        "status": "complete",
        "name": name,
        "result_count": api_result.get("count", 0),
        "stages": [{"name":"CNKI搜索","status":"完成","detail":f"找到{api_result.get('count',0)}条结果"}] + stages,
        "fields": {k:v for k,v in rec.fields.items() if v},
        "cleaned": cleaned,
        "missing_high_priority": rec.missing_high_priority(),
    })


def _get_cdp(endpoint: str):
    """GET CDP Proxy"""
    import urllib.request as _ur
    try:
        with _ur.urlopen(f"http://localhost:3456/{endpoint}", timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return []


def _clean_fields(rec) -> dict:
    """清洗脏数据：过滤人名杂质、校验生卒年、去重机构"""
    import re as _re
    cleaned = {}

    # 在职单位：去掉人名（2-3字中文名混在机构里的）
    inst = rec.fields.get("在职单位", "")
    if inst:
        # 去掉疑似人名的片段：跟在分号后面的2-3字中文
        parts = [p.strip() for p in inst.replace("；", ";").split(";")]
        clean_parts = []
        for p in parts:
            # 去掉纯人名（2-3字且不含"大学""学院""研究"等机构词）
            if len(p) <= 4 and not _re.search(r'大学|学院|研究|所|院|系|部|处|中心|实验室', p):
                continue
            # 去掉开头的人名（如"李春秋黑龙江八一农垦大学" → "黑龙江八一农垦大学"）
            p = _re.sub(r'^[一-龥]{2,3}(?=[一-龥]{4,}大学)', '', p)
            if p:
                clean_parts.append(p)
        if clean_parts:
            rec.fields["在职单位"] = "; ".join(clean_parts[:3])
            cleaned["在职单位"] = rec.fields["在职单位"]

    # 生卒年：严格校验
    bd = rec.fields.get("生卒年或个人活动日期", "")
    if bd:
        match = _re.match(r'(\d{4})\s*[-–—]\s*(\d{4})?', bd)
        if match:
            y1 = int(match.group(1))
            y2 = int(match.group(2)) if match.lastindex and match.lastindex >= 2 and match.group(2) else None
            valid = True
            # 出生年必须在1930-2010
            if y1 < 1930 or y1 > 2010:
                valid = False
            # 毕业年不能是未来，年龄不能超60
            if y2 and (y2 > 2026 or y2 - y1 > 60):
                valid = False
            # 出生年在1995后且无卒年或跨度<30年 → 教育经历年份，不是生卒年
            if y1 >= 1995:
                valid = False
            if valid:
                cleaned["生卒年或个人活动日期"] = rec.fields["生卒年或个人活动日期"]
            else:
                rec.fields["生卒年或个人活动日期"] = ""

    # 活动领域：去数字和多余符号
    field = rec.fields.get("活动领域", "")
    if field:
        field = _re.sub(r'\d+', '', field)  # 去数字
        field = _re.sub(r'[；;]{2,}', ';', field)  # 去重复分号
        field = field.strip(';；,， ')
        rec.fields["活动领域"] = field
        cleaned["活动领域"] = field

    return cleaned


def _fallback_results(name, api_result):
    return jsonify({"status": "results", "name": name,
        "result_count": api_result.get("count", 0),
        "papers": [{"title": t, "access": "HTML"} for t in api_result.get("titles", [])[:10]]})


def _parse_cnki_results(tab_id: str) -> dict:
    """从知网结果页解析论文列表"""
    body = page_text(tab_id)

    # 提取结果数量
    count = 0
    m = re.search(r'共找到\s*(\d+)\s*条结果', body)
    if m:
        count = int(m.group(1))

    # 提取论文条目
    papers = []
    js = """
var result = [];
var rows = document.querySelectorAll('tr');
rows.forEach(function(row) {
    var text = row.textContent.trim();
    var hasHTML = text.indexOf('HTML阅读') > -1;
    var hasDownload = text.indexOf('下载') > -1;
    if(hasHTML || hasDownload) {
        var lines = text.split('\\n').filter(function(l) { return l.trim(); });
        var title = lines[0] || '';
        var hasHtml = text.indexOf('HTML阅读') > -1 ? 'HTML' : '';
        var hasYuanban = text.indexOf('原版阅读') > -1 ? '原版' : '';
        result.push({
            title: title.substring(0, 80),
            access: hasHtml || hasYuanban || '下载',
            fullText: text.substring(0, 300)
        });
    }
});
JSON.stringify(result.slice(0, 15));
"""
    try:
        papers = json.loads(str(eval_js(tab_id, js)))
    except json.JSONDecodeError:
        pass

    return {"count": count, "papers": papers}


if __name__ == "__main__":
    from waitress import serve

    _load_state()
    os.makedirs(str(OUTPUT_DIR), exist_ok=True)

    print(f"\n  author_agent Web 服务")
    print(f"  http://127.0.0.1:8820")
    print(f"  数据目录: {OUTPUT_DIR}")
    print(f"  已加载 {len(pipeline.records)} 条记录\n")

    serve(app, host="127.0.0.1", port=8820)
