# 名称规范记录智能体 v1.1

网页搜捕 -> 结构化提取 -> dedup-librecord 匹配就绪

## v1.1 更新 (2026-05-13)

- 修复: 论文标题提取过滤表头行(不再把"题名/作者/来源"当论文标题)
- 修复: 前端JSON解析容错(服务异常时不再白屏)
- 修复: cdp_client.py import错误导致search崩溃(500)
- 修复: 生卒年清洗规则(1995年后年份拒绝)
- 优化: 在职单位区分教育/工作经历
- 优化: 邮箱/生年/领域仅从目标姓名所在句提取(防合著者污染)

## v1.0 功能

- 知网同步XHR搜索 + 多篇HTML全文自动打开
- 16个规范字段提取(论文目标句/官网全文)
- 必应搜索官网补全
- 数据清洗(合著者过滤/生卒年校验/教育-工作分离)
- Excel导出(dedup-librecord格式)

## 安装

```bash
pip install -r requirements.txt
```

## 使用

1. Chrome远程调试: chrome://inspect/#remote-debugging
2. CDP Proxy: node scripts/cdp-proxy.mjs
3. 启动服务: python server.py
4. 打开 http://127.0.0.1:8820

## 首次使用

Chrome知网页面手动搜索一次激活会话,之后全自动。
