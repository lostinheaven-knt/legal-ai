# Legal AI Toolkit

本地优先的命令行工具，用于单 SKU 电商合规预检。将精简的产品工作区转化为可操作的
EU/US Amazon 风险报告、Listing 声明修订建议、供应商证据请求以及结构化审计输出。

> Legal AI Toolkit 是一款 AI 辅助分诊工具。它不是法律意见、认证、产品清关，
> 也不能替代专业的合规审查。

## 功能概览

- 从 `product.yaml` 和 Listing 上下文中提取并规范化产品信息。
- 审查电商声明中的无依据、高风险或模糊表述。
- 使用本地护栏包对 EU、US 及 Amazon 合规风险进行分类。
- 检查供应商证据清单并生成差距分析请求。
- 生成 Markdown 报告、PDF 报告、供应商邮件、XLSX 证据表和 JSON 输出。
- 提供产品化的 LLM 错误信息，附带可操作的恢复建议。
- 支持确定性离线回退与 DeepSeek/OpenAI 兼容的 LLM 模式。

## 仓库结构

```text
.
├── src/legal_ai/
│   ├── cli.py           # CLI 入口 (Typer)
│   ├── commands/        # init、check、listing、evidence、report 子命令
│   ├── skills/          # 工作流技能（合规、声明、证据、PDF、报告）
│   ├── rules/           # 护栏包加载器与 Schema
│   ├── llm/             # LLM 客户端、提示词与 JSON Schema
│   ├── templates/       # Jinja2 模板（风险报告、修订稿、供应商邮件、专家审查）
│   └── models.py        # Pydantic 数据模型
├── README.md
├── README.zh-CN.md
└── pyproject.toml
```

仓库仅发布运行时代码、模板和项目元数据。本地实验、缓存、测试、文档、虚拟环境
及生成的工作区均默认忽略。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
legal-ai --help
```

安装开发依赖：

```bash
pip install -e ".[dev]"
```

## 快速开始

创建单 SKU 工作区：

```bash
legal-ai init demo-product
```

生成的工作区结构如下：

```text
demo-product/
├── product.yaml
├── listing.md
├── supplier-docs/
├── reports/
└── .legal-ai/
    ├── config.yaml
    └── audit-log.jsonl
```

编辑 `product.yaml`、`listing.md`，并放入供应商文档。然后运行：

```bash
legal-ai check demo-product --market EU,US --platform amazon --strict
```

生成的产物：

- `reports/risk-report.md`
- `reports/risk-report.pdf`
- `reports/listing-redline.md`
- `reports/evidence-gap.xlsx`
- `reports/supplier-email.md`
- `reports/structured-result.json`

## LLM 模式

工具支持确定性本地检查，也可接入 DeepSeek/OpenAI 兼容的 LLM 提供商。

```bash
export DEEPSEEK_API_KEY="..."
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
```

工作区配置：

```yaml
llm:
  enabled: auto        # auto、always 或 off
  provider: deepseek-compatible
  model: deepseek-chat
  timeout_seconds: 45
  max_retries: 1
  prompt_version: v1
privacy:
  local_first: true
  allow_supplier_doc_upload: false
```

常用模式：

```bash
legal-ai check demo-product --llm off
legal-ai check demo-product --llm always
```

`--llm always` 在提供商配置或 JSON Schema 校验失败时快速报错。
`--llm off` 保持完全本地化运行，结果可复现。

## 独立子命令

```bash
legal-ai listing review demo-product --market EU,US --platform amazon
legal-ai evidence gap demo-product --market EU,US --platform amazon
legal-ai report build demo-product          # 生成 .md、.pdf、.xlsx 和 .json
```

`report build` 在已安装 `reportlab` 且系统存在 CJK 字体时生成 PDF 风险报告
（支持 macOS 系统字体、Noto Sans CJK，或放置在 `src/legal_ai/assets/fonts/`
下的捆绑字体）。若报告仅含 ASCII 文本且未找到 CJK 字体，则使用内置的极简
PDF 写入器作为回退——无需额外依赖。

## 隐私模型

- 启用 LLM 模式时，产品元数据、受限的 Listing 文本、提示词合约以及证据清单
  可发送至配置的 LLM 提供商。
- 供应商文档全文上传默认关闭。
- 审计日志不记录 API 密钥、原始提示词和供应商文档全文。
- 每个工作区命令均记录输入哈希、输出路径、模型模式、提示词合约
  以及护栏包元数据。

## 护栏覆盖范围

当前护栏包聚焦于：

- EU 产品安全基础要求
- US FTC 声明实证基础要求
- Amazon 敏感品类文档提示

首个版本有意控制范围：单 SKU、EU/US、Amazon，提供实用的预检输出，
并明确标注不确定性。

## 安全边界

生成的报告不得声明产品合规、已获批、已认证、安全或可上市销售。
高风险、不确定、儿童用品、电子产品、医疗/健康、执法行动、召回
或强制性文件不明确等场景，应转交专业法律或合规人员处理。
