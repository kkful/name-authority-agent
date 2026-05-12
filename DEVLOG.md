# 名称规范记录智能体 — 开发流水日志

## 2026-05-12 最终状态

### 完整流程
```
输入姓名+机构 → 添加
  ↓ ① CNKI同步XHR搜索 → 注入DOM
  ↓ ② 逐篇打开HTML（最多5篇）→ 提取作者简介
  ↓ ③ 必应搜索官网 → 导航.edu.cn个人页
  ↓ ④ 论文+官网双来源合并提取字段
  ↓ ⑤ 数据清洗 → 保存Excel
```

### 提取字段（16个）
姓名/别名/性别/民族/学历/国籍/生卒年或个活动日期/籍贯/活动领域/受教育机构/在职单位/职业/职称/电子邮箱/发表的著作实体/控制号

### 关键文件
- server.py: Flask服务 + 搜索API + 提取管线
- author_agent/record.py: 字段提取（论文从目标句取，官网从全文取）
- author_agent/cnki_api.py: 知网同步XHR搜索 + 页面管理
- author_agent/cdp_client.py: CDP Proxy客户端封装
- static/index.html: Web前端界面
- entity_matching2/: Excel输出目录

## 2026-05-11 会话记录

### 背景调研
- 用户分析了超星发现系统与规范记录关联匹配的思路
- 两阶段策略：关联匹配 + 聚簇自动生成
- 区分特征：生卒年、学科领域、性别、籍贯、附属机构（参考RDA标准）
- 滚雪球策略：论文简介 → 官网 → 更丰富数据

### 实际操作验证

#### 1. B站排行榜测试 (CDP能力验证)
- 通过 API `api.bilibili.com/x/web-interface/ranking/v2` 直接获取排行榜
- 提取今日全站播放量前十视频 ✅

#### 2. 超星发现系统实操
- 访问 `fsso.zhizhen.com` → 机构登录页 → 河北大学
- 进入 `zhizhen.com` 发现系统主站
- 搜索"张伟 广东外语外贸大学"：188,935条结果
- 结果中已带机构标注（如"张伟（广东外语外贸大学中国语言文化学院）"）
- 问题：所有结果仅显示"文献传递"和"馆藏纸本资源"，无"电子全文"入口
- 结论：超星作为发现入口可用，但全文提取需走知网

#### 3. 知网完整搜捕验证
- 打开 `kns.cnki.net/kns8s/AdvSearch` 高级检索
- 切换到"作者发文检索"模式
- 遇到 React 受控组件障碍：JS 设置 input.value 不更新UI状态
- 使用原生setter + 事件分发仍不生效 → 最终请用户手动填入
- 用户手动搜索后：39条结果，大部分有"HTML阅读"
- HTML阅读链接 `bar.cnki.net` token一次性，不能复用URL
- clickAt（真实CDP鼠标事件）成功打开HTML阅读（新tab）
- 提取作者简介："张伟，广东外语外贸大学中国语言文化学院教授..."（极简版）
- 滚雪球第二步：搜索引擎 → `zwxy.gdufs.edu.cn/info/1272/9604.htm` 官网个人页
- 官网信息丰富：性别、籍贯、学历、博后、研究方向、著作...
- 滚雪球第三步：《探索与争鸣》期刊官网 → 生年1979 ✅

#### 4. 站点经验积累
- 保存 `cnki.net.md` 站点经验文件
- 关键发现：React受控组件、bar.cnki.net token一次性、首页触发验证码、高级检索不触发
- 人工介入弹窗机制：注入红色通知条

### 代码产出

#### 项目结构 `E:\规范文档\`
```
author_agent/          # Python包
├── __init__.py        # 公共API
├── config.py          # 全局配置（路径/模型/来源）
├── schema.py          # 字段定义+RDA优先级+来源优先级
├── record.py          # AuthorRecord类+多来源合并+Excel输出
├── extractor.py       # LLM提取器（规则预提取+prompt模板+API后端）
├── pipeline.py        # 流水线编排（喂入→提取→检查→输出）
├── cdp_client.py      # CDP Proxy客户端（浏览器自动化封装）
└── cli.py             # CLI入口

server.py              # Flask Web服务 + 搜索API (端口8820)
static/index.html      # 前端SPA（档案目录卡片风格）
setup.py               # pip install -e 安装
start_server.bat       # 手动启动脚本
demo_full_pipeline.py  # 端到端演示
entity_matching2/      # 输出目录（dedup就绪）
```

#### 后端 API
| 端点 | 方法 | 功能 |
|------|------|------|
| /api/pipeline/status | GET | 流水线状态 |
| /api/feed | POST | 喂入网页文本 |
| /api/apply | POST | 应用LLM提取结果 |
| /api/check | GET | 质量检查 |
| /api/save | POST | 保存Excel+状态 |
| /api/record/<name> | GET/PUT | 查看/编辑记录 |
| /api/batch | POST | 批量添加目标 |
| /api/search/start | POST | 启动知网搜捕 |
| /api/search/continue/<name> | POST | 继续搜捕流程 |
| /api/search/open_html/<name> | POST | 打开HTML全文 |
| /api/search/extract_bio/<name> | POST | 提取作者简介 |

#### 前端设计
- 美学：档案目录卡片风格
- 字体：Playfair Display + Source Serif 4 + JetBrains Mono
- 配色：墨色 #2c2424 + 纸色 #f5f0e8 + 馆藏印红 #c75b39 + 古铜金 #b8956a
- 布局：左侧窄边栏 + 卡片网格 + 右侧滑出详情面板
- SVG噪点纸纹背景

#### dedup-librecord 分析
- 输入：按姓名分组的Excel文件，14个标准字段
- 4种匹配策略：全字段嵌入/单字段加权/混合硬匹配/混合软匹配
- 输出：带聚类ID的Excel
- 字段权重：生卒年0.20、著作0.20、籍贯0.20为最高

### 遗留问题 (明天继续)

1. **index.html 搜捕JS未完成** — 卡片已有搜捕按钮和CSS，但 `startSearch`、`sanitize`、`continueSearch`、`openFirstHTML` 等函数在编辑中被取消
2. 知网React表单自动填入仍需攻克
3. 端到端测试：启动服务→搜捕→提取→导出→dedup匹配
4. server.py 中的 `import time` 重复（`import time` 和 `import time as _time` 同时存在）

### 环境依赖
- Python 3.13 + Flask + waitress + pandas + openpyxl
- Chrome + CDP Proxy (web-access skill)
- Node.js 22+ (CDP Proxy依赖)
- dedup-librecord: E:\dedup-librecord\ (sentence-transformers, scipy)
