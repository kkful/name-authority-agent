"""CDP Proxy 客户端 - 浏览器自动化操作封装

封装 web-access skill 的 CDP Proxy HTTP API (localhost:3456),
提供浏览器标签管理、JS执行、鼠标点击、键盘输入、页面文本提取等功能。

依赖:
    web-access skill 提供的 CDP Proxy (localhost:3456)
    需要 Chrome 开启远程调试: chrome://inspect/#remote-debugging

核心函数:
    new_tab(url)        - 创建新标签
    eval_js(tab, js)    - 执行 JavaScript
    click_at(tab, sel)  - 真实鼠标点击(CDP Input.dispatchMouseEvent)
    type_text(tab,sel,t) - CDP 物理键盘输入
    page_text(tab)      - 获取页面可见文本
    inject_notification(tab, msg) - 注入红色通知弹窗
    open_html_reading(tab)  - 点击知网搜索结果中的 HTML阅读 链接
    extract_author_bio(tab) - 从 HTML 阅读页面提取作者简介
"""

import json
import time
import urllib.request
import urllib.error

CDP_PROXY = "http://localhost:3456"
