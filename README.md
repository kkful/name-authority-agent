# 名称规范记录智能体 v1.0

网页搜捕 → 结构化提取 → dedup-librecord 匹配就绪

## 功能

- **知网搜捕**: 同步XHR搜索 + 多篇HTML全文自动打开
- **字段提取**: 从论文作者简介和官网个人页提取16个规范字段
- **官网补全**: 必应搜索找到.edu.cn个人页,自动补全字段
- **数据清洗**: 自动过滤合著者数据、校验生卒年、分离教育/工作经历
- **Excel导出**: dedup-librecord格式,直接参与语义匹配

## 安装

```bash
pip install -r requirements.txt
```

## 使用

1. 启动Chrome远程调试: chrome://inspect/#remote-debugging
2. 启动CDP Proxy: node scripts/cdp-proxy.mjs
3. 启动服务: python server.py
4. 打开 http://127.0.0.1:8820

## 首次使用

在Chrome知网页面手动搜索一次激活会话,之后所有搜捕全自动。

## 项目结构

```
author_agent/        # Python包
  record.py          # 字段提取（论文目标句/官网全文）
  cnki_api.py        # 知网同步XHR搜索
  cdp_client.py      # CDP Proxy客户端
  schema.py          # 16个字段定义
server.py            # Flask Web服务
static/index.html    # 前端界面
entity_matching2/    # Excel输出
```
