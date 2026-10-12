# CLAUDE.md

WenQuest Ops：给美国和国际中小企业的分模块 AI 集成平台（产品方案见 `docs/plan.md`，决策见 `docs/adr/`）。
以 ERPNext 为底座，把订单、库存、采购、质量连成一张数据网，AI 只起草、由人确认。企业按我们的教程用 AI 自己搭建和定制；
我们卖课程和托管接口。项目负责人：Guoqing (Eddie) Zhang。

## 语言

- 产品界面、代码、注释、提交信息、测试数据：英文
- 计划、ADR、给项目负责人的说明：中文（术语可附英文）
- 和项目负责人交流：中文

## 工作方式

- 先定计划再动手：范围、接口、数据、校验规则的变更先改 `docs/plan.md` 或写 ADR，项目负责人同意后再写代码
- 一次只做一个 issue；超出范围的另开 issue
- 从 `main` 开分支 `p<期>/<简述>`（如 `p1/company-manifest`）；所有改动走 PR，不直接推 `main`
- 提交信息 `P<期>: <做了什么>`，正文写原因和关联 issue
- 节奏放慢：项目负责人一个人做，预算是每月 Claude 套餐加 GitHub Pro；不赶工期

## 必须遵守

- 不得编造数据：演示企业是虚构的并明确标注；真实企业的数据缺了就标“unknown”，不得猜
- AI 只起草：任何写入 ERPNext 或对外发送的动作，都要人在界面上确认；AI 的每次运行留记录
- 校验遇到缺失数据结果为 unknown，不得判为 pass
- 不得跳过、删除或弱化已有测试；测试不联网、不调用真实 LLM
- 密钥只从环境变量读取，不入仓库；企业数据不入仓库
- 不修改 ERPNext 源码：只通过它的 REST API 与官方镜像使用（保持与 GPLv3 的边界清楚，ADR-0001）
- 每次会话结束前运行 `python -m ruff check .` 和 `python -m pytest`，结果写进 PR

## 命令

```bash
pip install -e ".[dev]"
python -m ruff check .
python -m pytest -v
```
