# 名称规范记录智能体 v1.1

网页搜捕 -> 结构化提取 -> dedup-librecord 匹配就绪

## 环境要求

- **Python 3.9+** (推荐 3.11+)
- **Node.js 22+** (CDP Proxy 依赖)
- **Chrome 浏览器** (远程调试模式)
- **web-access skill** (Claude Code 插件，提供 CDP Proxy)

## 快速部署 (5分钟)

### 1. 克隆项目

```bash
git clone https://github.com/kkful/name-authority-agent.git
cd name-authority-agent
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 Chrome 远程调试

打开 Chrome，地址栏输入:
```
chrome://inspect/#remote-debugging
```
勾选 **"Allow remote debugging for this browser instance"**，重启 Chrome。

### 4. 启动 CDP Proxy

```bash
# 在项目目录下，确保 web-access skill 已安装
node C:/Users/Administrator/.claude/skills/web-access/scripts/cdp-proxy.mjs
```

> 或者使用 web-access skill 的启动脚本:
> ```bash
> node C:/Users/Administrator/.claude/skills/web-access/scripts/check-deps.mjs
> ```

### 5. 启动 Web 服务

```bash
python server.py
```

### 6. 打开管理界面

浏览器访问: **http://127.0.0.1:8820**

### 7. 首次使用

在界面添加作者 + 机构后，Chrome 中会自动打开知网页面。**手动搜索一次**以激活会话（仅首次需要），之后所有搜捕全自动。

## 项目结构

```
author_agent/        # Python核心包
  cdp_client.py      # CDP Proxy 客户端
  cnki_api.py        # 知网同步XHR搜索
  record.py          # 字段提取(论文/官网)
  schema.py          # 16个字段定义
server.py            # Flask Web服务
static/index.html    # Web前端界面
entity_matching2/    # Excel输出目录
```

## 问题排查

| 问题 | 解决 |
|------|------|
| CDP Proxy 未运行 | 确认 Chrome 已开启远程调试，Proxy 已启动 |
| 知网搜索无结果 | Chrome 知网页面手动搜索一次激活 Classid |
| 搜捕卡住不动 | 刷新 http://127.0.0.1:8820 重新添加 |
| 保存Excel失败 | 关闭已打开的 Excel 文件再保存 |
| 字段不准确 | 官网数据会自动覆盖论文数据，优先补全官网 |

## v1.1 更新 (2026-05-13)

- 修复: 论文标题过滤表头行
- 修复: JSON解析容错
- 修复: cdp_client import错误
- 优化: 教育/工作经历分离
- 优化: 邮箱/生年防合著者污染
