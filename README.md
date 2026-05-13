# 名称规范记录智能体 v1.2

网页搜捕 -> 结构化提取 -> dedup-librecord 匹配就绪

## v1.2 更新 (2026-05-13)

**关键修复**:
- LLM优先级0→20: DeepSeek提取的字段不再被静默拒绝,现在最高优先覆盖
- 移除"先清空再提取"黑洞: 官网格式不匹配时字段不再被永久清空
- 机构baseline: 搜索时机构先写入在职单位,后续官网/LLM覆盖
- Bing链接提取增强: 直接搜.edu.cn,提高命中率
- 邮箱空格容错: 支持"邮 箱"格式
- 启动脚本自启CDP Proxy

**新增**:
- LLM自适应提取: 论文+官网文本合并,DeepSeek API自动提取结构化字段
- config.yaml配置文件: API Key集中管理
- DeepSeek集成: 兼容OpenAI协议,国内可用

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

### 3. 配置 DeepSeek API Key
编辑 `config.yaml`,填入Key:
```yaml
LLM_PROVIDER: deepseek
LLM_MODEL: deepseek-chat
DEEPSEEK_API_KEY: sk-xxxxxxxxxxxxxxxx
```
> Key在 https://platform.deepseek.com 获取

### 4. Chrome远程调试
```
chrome://inspect/#remote-debugging
勾选 "Allow remote debugging for this browser instance"
```

### 5. 启动
双击 `start_server.bat` 或 `python server.py`
访问 http://127.0.0.1:8820

### 6. 首次激活
知网页面手动搜索一次,之后全自动

## 问题排查
| 问题 | 解决 |
|------|------|
| CDP Proxy未运行 | 确认Chrome远程调试已开启 |
| 字段为空 | 填机构名,确认config.yaml中API Key正确 |
| LLM提取跳过 | 确认DeepSeek API Key已填写且有余额 |
| 保存Excel失败 | 关闭已打开的Excel文件 |
