# 名称规范记录智能体 v1.2

网页搜捕 -> 结构化提取 -> dedup-librecord 匹配就绪

## v1.2 更新 (2026-05-13)

- **LLM自适应提取**: 论文+官网文本合并,DeepSeek API自动提取结构化字段
- **零规则依赖**: 无论官网什么格式,LLM读语义自适应提取
- **DeepSeek集成**: 兼容OpenAI协议,国内可用

## v1.1 更新

- 修复: 论文标题过滤表头行
- 修复: JSON解析容错
- 修复: cdp_client import错误
- 优化: 教育/工作经历分离

## 快速部署

### 1. 克隆项目

```bash
git clone https://github.com/kkful/name-authority-agent.git
cd name-authority-agent
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 DeepSeek API Key（v1.2 新增）

编辑 `config.yaml`，填入你的 DeepSeek API Key:

```yaml
LLM_PROVIDER: deepseek
LLM_MODEL: deepseek-chat
DEEPSEEK_API_KEY: sk-xxxxxxxxxxxxxxxx
```

> Key 在 https://platform.deepseek.com 获取，新用户有免费额度。
> 不填 Key 也能用，只是最后一步 LLM 提取会跳过，字段由正则规则提取。

### 4. 配置 Chrome 远程调试

打开 Chrome，地址栏输入:
```
chrome://inspect/#remote-debugging
```
勾选 **"Allow remote debugging for this browser instance"**，重启 Chrome。

### 5. 启动 CDP Proxy

```bash
node C:/Users/Administrator/.claude/skills/web-access/scripts/check-deps.mjs
```

### 6. 启动 Web 服务

```bash
# 方式一: 双击 start_server.bat
# 方式二:
python server.py
```

### 7. 打开界面

浏览器访问: **http://127.0.0.1:8820**

### 8. 首次激活

知网页面第一次会弹通知，手动搜索一次后，所有搜捕全自动。

## 重启方式

修改 `config.yaml` 后需要重启:

```bash
# 关闭正在运行的服务 (Ctrl+C)
# 然后重新启动:
python server.py
```

或直接双击 `start_server.bat`。

## 项目结构

```
author_agent/        # Python核心包
  record.py          # 字段提取(正则+LLM)
  extractor.py       # LLM提取器(DeepSeek/Claude/OpenAI)
  cnki_api.py        # 知网同步XHR搜索
  cdp_client.py      # CDP Proxy客户端
  schema.py          # 16个字段定义
config.yaml          # 配置文件(API Key等)
server.py            # Flask Web服务
start_server.bat     # 一键启动脚本
static/index.html    # Web前端
entity_matching2/    # Excel输出
```

## 问题排查

| 问题 | 解决 |
|------|------|
| CDP Proxy 未运行 | 确认Chrome远程调试已开启,Proxy已启动 |
| 知网搜索无结果 | Chrome知网页面手动搜索一次激活 |
| LLM提取跳过 | 确认config.yaml中DEEPSEEK_API_KEY已填写正确 |
| 保存Excel失败 | 关闭已打开的Excel文件 |
| 字段不准确 | LLM提取会自动覆盖补全,无需手动调整 |
