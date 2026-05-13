"""V2 论文采集器 — 搜作者 → 全文量采集 → Excel

用法:
    python collector.py 张伟 --max 10  # 最多打开10篇HTML
"""
import sys, os, json, time, re, urllib.request
import pandas as pd

sys.path.insert(0, r"E:\名称规范系统\旧规范文档")
from author_agent.cdp_client import new_tab, close_tab, eval_js, click_at, page_text

PROXY = "http://localhost:3456"
OUTPUT_DIR = r"E:\名称规范系统\新规范文档系统\collected"

def get(path):
    with urllib.request.urlopen(PROXY + path) as r:
        return json.loads(r.read())

def post(path, data):
    body = data.encode("utf-8")
    req = urllib.request.Request(PROXY + path, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

def find_or_create_cnki_tab():
    """找已激活的知网标签，没有则创建并提示"""
    tabs = get("/targets")
    for t in tabs:
        if "AdvSearch" in t.get("url", ""):
            try:
                r = eval_js(t["targetId"], "JSON.parse(window.cnkiSearch.getSearchJsonInfo()).Classid")
                if r and str(r).strip():
                    return t["targetId"]
            except: pass
    # 创建新标签
    for t in tabs:
        if "AdvSearch" in t.get("url", ""):
            try: get("/close?target=" + t["targetId"])
            except: pass
    r = get("/new?url=https://kns.cnki.net/kns8s/AdvSearch")
    time.sleep(4)
    post(f"/eval?target={r['targetId']}",
        'var d=document.createElement("div");d.style.cssText="position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#27ae60;color:#fff;padding:20px 40px;font-size:18px;z-index:999999;border-radius:8px;text-align:center";d.innerHTML="<b>请手动搜索一次激活页面</b><br>切换到「作者发文检索」-> 填入任意搜索条件 -> 点检索";document.body.appendChild(d);"ok"')
    print("   -> 请在Chrome知网页面手动搜索一次激活，然后重新运行采集器")
    sys.exit(0)

def search_author(tab_id, author_name):
    """同步XHR搜索作者，返回HTML"""
    js = 'var cs=window.cnkiSearch;var base=JSON.parse(cs.getSearchJsonInfo());' + \
         'base.QNode.QGroup=[{Key:"S",Title:"",Logic:0,Items:[],ChildItems:[]}];' + \
         'base.QNode.QGroup[0].ChildItems=[{Key:"a",Title:"",Logic:0,Items:[{Key:"a",Title:"",Logic:0,Field:"AU",Operator:"DEFAULT",Value:"' + author_name + '",Value2:""}],ChildItems:[]}];' + \
         'var qj=JSON.stringify(base);var x=new XMLHttpRequest();' + \
         'x.open("POST","/kns8s/brief/grid",false);' + \
         'x.setRequestHeader("Content-Type","application/x-www-form-urlencoded;charset=UTF-8");' + \
         'x.send("boolSearch=true&QueryJson="+encodeURIComponent(qj));' + \
         'window.__h=x.responseText;' + \
         'var m=x.responseText.match(/共找到<\\/span>\\s*<em>(\\d+)<\\/em>/);' + \
         'var totalCount=m?parseInt(m[1]):0;' + \
         'var titles=[];var tr=/<a[^>]*class="fz14"[^>]*>([^<]+)<\\/a>/g;var tm;' + \
         'while(tm=tr.exec(x.responseText)){var tt=tm[1].trim();if(tt.length>3&&tt!="题名"&&tt!="作者"&&tt!="来源")titles.push(tt)};' + \
         'JSON.stringify({count:totalCount,titles:titles,len:x.responseText.length})'
    r = eval_js(tab_id, js)
    try: return json.loads(str(r))
    except: return {"count":0, "titles":[], "len":0}

def collect_all_papers(tab_id, author_name, titles, max_open=20):
    """全量采集：有HTML则打开全文，无则导航详情页"""
    meta_js = 'var html=window.__h;var papers=[];var rows=html.split("<tr");' + \
              'rows.forEach(function(r){' + \
              'var t=r.replace(/<[^>]+>/g," ").replace(/\\s+/g," ").trim();' + \
              'if(t.length>20&&t.indexOf("题名")===-1&&t.indexOf("操作")===-1)papers.push(t.substring(0,300));' + \
              '});JSON.stringify(papers)'
    r = eval_js(tab_id, meta_js)
    try: metadata = json.loads(str(r))
    except: metadata = []

    MAX_PAPERS = 200
    actual_total = len(metadata)
    if actual_total == 0: actual_total = len(titles)
    total = min(actual_total, MAX_PAPERS)
    if actual_total > MAX_PAPERS:
        print(f"  搜索结果 {actual_total} 条，取前{MAX_PAPERS}篇")
    else:
        print(f"  搜索结果 {total} 条，全部采集")

    eval_js(tab_id, 'var bb=document.getElementById("briefBox");if(bb){bb.innerHTML=window.__h};"ok"')
    time.sleep(0.5)
    r = eval_js(tab_id, 'var c=0;document.querySelectorAll("a").forEach(function(a){if(a.textContent.indexOf("HTML阅读")>-1)c++});String(c)')
    html_count = int(r) if r and str(r).isdigit() else 0
    print(f"  其中 {html_count} 篇有HTML阅读")

    papers = []
    html_opened = 0

    for i in range(total):
        idx = i + 1
        try:
            paper = {"序号": idx, "论文元数据": metadata[i] if i < len(metadata) else "",
                     "论文标题": titles[i] if i < len(titles) else metadata[i][:50] if i < len(metadata) else "",
                     "作者简介原文": "", "页面头部信息": "", "来源": "仅元数据"}

            if i > 0:
                eval_js(tab_id, 'var bb=document.getElementById("briefBox");if(bb){bb.innerHTML=window.__h};"ok"')
                time.sleep(0.3)

            has_html_link = i < html_count
            can_open_html = has_html_link and html_opened < max_open
            is_html = False

            if can_open_html:
                eval_js(tab_id, f'var c=0;document.querySelectorAll("a").forEach(function(a){{if(a.textContent.indexOf("HTML阅读")>-1){{c++;if(c=={i+1})a.id="__ht{i+1}"}}}});"m"')
                time.sleep(0.2)
                click_body = f"#__ht{i+1}".encode("utf-8")
                req = urllib.request.Request(f"{PROXY}/clickAt?target={tab_id}", data=click_body, method="POST")
                req.add_header("Content-Type", "text/plain")
                with urllib.request.urlopen(req, timeout=30) as rp:
                    cr = json.loads(rp.read())
                if cr.get("clicked"):
                    time.sleep(3)
                    html_tab = ""
                    for t in get("/targets"):
                        if "HTML" in t.get("title","") or "reader" in t.get("url",""):
                            html_tab = t["targetId"]
                    if html_tab:
                        full_text = page_text(html_tab)
                        if full_text and len(full_text) > 100:
                            txt = full_text
                            result = {}
                            result["标题"] = txt.split("\n")[0].strip()[:100]
                            abs_m = re.search(r'(?:中文\s*)?摘要[：:]\s*([\s\S]+?)(?:关键词|Key\s*words|Abstract|基金|收稿|$)', txt)
                            if not abs_m:
                                abs_m = re.search(r'摘要[：:]\s*([\s\S]+?)(?:关键词|Key\s*words|Abstract|基金|收稿|$)', txt)
                            if abs_m: result["摘要"] = abs_m.group(1).strip()[:800]
                            kw_m = re.search(r'(关键词[：:][^\n]+)', txt)
                            if kw_m: result["关键词"] = kw_m.group(1).strip()[:200]
                            fund_m = re.search(r'(基金[：:][^\n]+)', txt)
                            if fund_m: result["基金"] = fund_m.group(1).strip()[:200]
                            bio_m = re.search(r'作者简介[：:]\s*([\s\S]+?)(?:收稿日期|Received|$)', txt)
                            if bio_m: paper["作者简介原文"] = bio_m.group(1).strip()[:500]
                            date_m = re.search(r'(收稿日期[：:][^\n]+)', txt)
                            if date_m: result["收稿日期"] = date_m.group(1).strip()[:50]
                            parts = [f"{k}:{v}" for k,v in result.items() if v]
                            paper["页面头部信息"] = "\n---\n".join(parts)
                            paper["来源"] = "HTML阅读"
                            is_html = True
                            html_opened += 1
                        close_tab(html_tab)

            if not has_html_link and not paper.get("页面头部信息"):
                raw_html = str(eval_js(tab_id, 'window.__h'))
                detail_urls = re.findall(r'/kcms2/article/abstract\?v=[^"&\']+', raw_html)
                if not detail_urls:
                    detail_urls = re.findall(r'/kcms2/article/abstract\?v=[^"\']+', raw_html)
                if detail_urls and i < len(detail_urls):
                    detail_url = "https://kns.cnki.net" + detail_urls[i].replace("&amp;","&")
                    r = get("/new?url=" + urllib.request.quote(detail_url, safe=':/?=&'))
                    d_tab = r.get("targetId","")
                    if d_tab:
                        time.sleep(3)
                        d_txt = page_text(d_tab)
                        if d_txt and len(d_txt) > 100:
                            result = {}
                            lines = d_txt.split("\n")
                            title = ""
                            for line in lines:
                                s = line.strip()
                                if s and s not in ("总库","检索","CNKI AI","") and "http" not in s and len(s) > 5:
                                    title = s[:100]; break
                            result["标题"] = title
                            abs_idx = d_txt.find("摘要")
                            if abs_idx > -1:
                                author_block = d_txt[len(title):abs_idx].strip()[:500]
                                if author_block: result["作者机构"] = author_block.replace("\n"," ")[:400]
                            abs_m = re.search(r'摘要[：:]\s*([\s\S]+?)(?:关键词|Key\s*words|基金|专辑|专题|分类|$)', d_txt)
                            if abs_m: result["摘要"] = abs_m.group(1).strip()[:800]
                            kw_m = re.search(r'关键词[：:]\s*([^\n]+)', d_txt)
                            if kw_m: result["关键词"] = "关键词:" + kw_m.group(1).strip()[:200]
                            fund_m = re.search(r'基金[资助]?[：:]\s*([^\n]+)', d_txt)
                            if fund_m: result["基金"] = "基金:" + fund_m.group(1).strip()[:200]
                            for field in ["专辑","专题","分类号","在线公开时间"]:
                                fm = re.search(rf'{field}[：:]\s*([^\n]+)', d_txt)
                                if fm: result[field] = f"{field}:{fm.group(1).strip()[:100]}"
                            parts = [v for v in result.values() if v]
                            paper["页面头部信息"] = "\n---\n".join(parts) if parts else d_txt[:500]
                            paper["来源"] = "知网详情页"
                        close_tab(d_tab)
                if not paper.get("来源"):
                    meta = metadata[i] if i < len(metadata) else ""
                    paper["页面头部信息"] = meta[:500]
                    paper["来源"] = "XHR元数据"

            tag = "HTML" if is_html else ("详情" if paper.get("来源")=="知网详情页" else "META")
            print(f"    [{idx}/{total}] {tag} {paper['论文标题'][:50]}")
            papers.append(paper)
            time.sleep(0.3)

        except Exception as e:
            import traceback
            print(f"    [{idx}] ERROR: {e}")
            print(f"    {traceback.format_exc()[-200:]}")
            paper = {"序号": idx, "论文标题": titles[i] if i < len(titles) else "",
                     "页面头部信息": f"采集失败: {str(e)}", "来源": f"失败:{str(e)[:50]}"}
            papers.append(paper)

    return papers

def save_to_excel(papers, author_name):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df = pd.DataFrame(papers)
    ts = time.strftime("%H%M%S")
    path = os.path.join(OUTPUT_DIR, f"{author_name}_论文采集_{ts}.xlsx")
    df.to_excel(path, index=False)
    print(f"\n已保存 {len(papers)} 篇论文 -> {path}")
    return path

def collect(author_name, max_papers=20):
    print(f"\n{'='*50}")
    print(f"论文采集: {author_name}")
    print(f"{'='*50}")
    print("1. 连接知网...")
    tab = find_or_create_cnki_tab()
    print(f"   Tab: {tab[:20]}")
    print(f"2. 搜索 {author_name}...")
    result = search_author(tab, author_name)
    print(f"   结果: {result.get('count',0)} 条 (当前第1页)")
    if int(result.get("count", 0)) == 0:
        print("   未找到结果!"); return None
    print(f"3. 全量采集论文...")
    papers = collect_all_papers(tab, author_name, result.get("titles",[]), max_papers)
    print(f"4. 保存Excel...")
    return save_to_excel(papers, author_name)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python collector.py <姓名> [--max N]")
        sys.exit(1)
    name = sys.argv[1]
    max_p = 20
    if "--max" in sys.argv:
        idx = sys.argv.index("--max")
        max_p = int(sys.argv[idx+1])
    collect(name, max_p)
