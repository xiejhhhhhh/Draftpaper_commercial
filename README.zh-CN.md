# DraftPaper CLI

[![AI Research Workflow](https://img.shields.io/badge/AI-Research%20Workflow-5C4D7D?style=flat-square)](#)
[![Literature Analysis](https://img.shields.io/badge/Literature-Analysis-1D7874?style=flat-square)](#)
[![Citation Evidence](https://img.shields.io/badge/Citation-Evidence-4C956C?style=flat-square)](#)
[![BibTeX](https://img.shields.io/badge/BibTeX-Reference%20Library-3A506B?style=flat-square)](#)
[![Local First](https://img.shields.io/badge/Local-First-E07A5F?style=flat-square)](#)
[![Python CLI](https://img.shields.io/badge/Python-CLI-3776AB?style=flat-square&logo=python&logoColor=white)](./pyproject.toml)
[![Open Core](https://img.shields.io/badge/Open--core-Public%20Literature%20Layer-8A5A44?style=flat-square)](#)

中文 | [English](README.md)

DraftPaper CLI 是一个本地优先的科研论文流程化写作引擎。它把研究 idea、本地数据、已跑通的方法代码、结果文件和可追溯参考文献证据，组织成分阶段的 LaTeX 论文初稿。核心能力是 Python package + CLI；Codex skill、桌面端、Web UI、未来 API/SaaS 都应该调用同一套核心能力，而不是重复实现。

## 它能做什么

DraftPaper CLI 把一篇论文拆成一个本地项目目录，并通过明确阶段推进：创建项目、文献检索、目标期刊模板理解、research plan、Introduction、Data、Methods、Results、Discussion、LaTeX 组装、PDF 审阅和质量门检查。

参考文献流程优先使用免费检索源，包括 Semantic Scholar、arXiv、Crossref 和可选 SerpApi。系统会输出 BibTeX、citation evidence、文献综述笔记、HTML 文献摘要，并按 `idea`、`data`、`methods` 记录每篇文献支撑的论文部分。当 data/methods 文献缺少可读 abstract 时，DraftPaper 会通过 `paper_fetch_adapter.py` 调用项目内 vendored 的 `paper-fetch-skill`，尝试抓取全文 Markdown/JSON 作为证据。

## 核心能力

- 单篇论文本地项目目录模型和阶段 manifest。
- 支持阶段状态机、回退重跑、stale 标记和项目验证。
- `idea`、`data`、`methods` 三类上下文文献检索。
- 用 `citation_evidence.csv` 追踪每个引用支撑的论断。
- 目标期刊 profile 阶段，用于限制 LaTeX 模板和写作规范。
- Methods 硬门槛：必须先跑通本地方法代码。
- Result validity gate：结果不足时回退 data/method/research plan。
- Results 禁止文献引用。
- LaTeX 组装和可选本地 PDF 编译。
- Quality gate 检查引用、结果文件、stale 阶段和期刊模板。
- Codex skill wrapper 只是调用层，不承载核心业务逻辑。

## 公开范围

这个公开仓库定位为可运行的 CLI 基础框架。README 不展开商业化编排细节、prompt 配方、产品策略和不同学科的私有写作规则。这些内容更适合保存在私有部署文档或商业版 wrapper 仓库中。

## 项目结构

```text
draftpaper_cli/                 # 核心 Python package 和 CLI 阶段
codex_skills/draftpaper-workflow # 可选 Codex skill wrapper
docs/                           # 工作流设计和优先级指南
tests/                          # 单元测试
third_party/paper-fetch-skill/   # vendored MIT paper-fetch runtime
github_submit/                  # GitHub 提交材料和说明
```

本地生成的论文项目放在 `projects/`，并默认被 git 忽略，避免把研究数据、生成稿件、全文缓存和结果文件上传到公开仓库。

## 快速开始

### 在 Codex 中使用

这个项目的主要使用方式不是让用户手动敲每一条 CLI 命令，而是让 Codex 读取本仓库并替你调用 DraftPaper CLI。把仓库克隆到本地后，在 Codex 中打开或指向该仓库目录，然后直接用自然语言说：

```text
请使用 C:\Draftpaper_commercial 里的 DraftPaper CLI，基于我的 idea 创建论文项目、检索文献、生成 research plan，并告诉我哪些阶段被阻塞。
```

Codex 应该负责运行对应 CLI 命令、读取生成的本地项目文件，并汇报下一步。下面的 `draftpaper` 命令是底层接口，主要用于调试、自动化脚本或不通过 Codex 使用时，并不是要替代和 Codex 的正常对话。

分阶段工作时，Codex 应该先调用总控层：

```powershell
python -m draftpaper_cli.cli status --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli detect-artifact-drift --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli sync-artifact-stale --project C:\DraftPaper_CLI\projects\your_project
```

### 一键本地安装

在你希望保存项目的目录中运行下面这条命令。它会克隆私有仓库，创建本地虚拟环境，安装 DraftPaper CLI，并打印 CLI 帮助信息。`paper-fetch-skill` 已经 vendored 在 `third_party/paper-fetch-skill`，只有需要全文抓取时再单独安装。

```powershell
powershell -ExecutionPolicy Bypass -Command "git clone https://github.com/xiejhhhhhh/Draftpaper_commercial.git; cd Draftpaper_commercial; py -3 -m venv .venv; .\.venv\Scripts\python -m pip install -U pip; .\.venv\Scripts\python -m pip install -e .; .\.venv\Scripts\draftpaper --help"
```

可选安装全文抓取 runtime：

```powershell
.\.venv\Scripts\python -m pip install -e third_party\paper-fetch-skill
```

安装后，也可以在仓库根目录中直接使用 `draftpaper` 命令：

```powershell
.\.venv\Scripts\draftpaper create-project --root .\projects --idea "你的研究idea" --field "machine learning astronomy" --target-journal APJS
.\.venv\Scripts\draftpaper status --project .\projects\your_project
.\.venv\Scripts\draftpaper run-pipeline --project .\projects\your_project
.\.venv\Scripts\draftpaper search-literature --project .\projects\your_project --query "topic keywords"
.\.venv\Scripts\draftpaper validate-project --project .\projects\your_project
```

如果只想快速确认 CLI 能运行，不进行联网文献检索，可以执行：

```powershell
.\.venv\Scripts\draftpaper create-project --root .\projects --idea "X-ray flaring source classification" --field "machine learning astronomy" --target-journal APJS
.\.venv\Scripts\draftpaper validate-project --project .\projects\x-ray-flaring-source-classification
```

### 开发模式安装

```powershell
python -m pip install -e .
python -m draftpaper_cli.cli create-project --root C:\DraftPaper_CLI\projects --idea "你的研究idea" --field "machine learning astronomy" --target-journal APJS
python -m draftpaper_cli.cli status --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\your_project --query "topic keywords"
python -m draftpaper_cli.cli generate-analysis-code --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli validate-project --project C:\DraftPaper_CLI\projects\your_project
```

运行测试：

```powershell
python -m unittest discover -s tests
```

## 当前实现状态

CLI 已经实装总控层命令（`status`、`checkpoint`、`resume`、`run-pipeline`）、基于 hash 的 stale 同步命令（`detect-artifact-drift`、`sync-artifact-stale`），以及项目状态、文献检索、目标期刊 profile、research plan、Introduction、数据清单和可行性检查、method plan 收集、基于文献和 methods 描述的 baseline 分析代码生成、方法代码运行验证、Methods 撰写、结果有效性检查、结果清单、Results 撰写、Discussion、LaTeX 组装、PDF 编译和最终质量检查等阶段命令。

每个项目现在都会带有 DraftPaper Passport：`project_passport.yaml`，以及 append-only 的 `artifact_ledger.jsonl`、`checkpoint_ledger.jsonl`、`integrity_ledger.jsonl`。这些文件记录项目 artifact、hash、人工 checkpoint 和 integrity event，方便换电脑迁移，也避免依赖 Codex 对话记忆来判断项目状态。

当被追踪 artifact 的 hash 发生变化时，`status` 会返回 `pipeline_state=drift_detected`，并建议先运行 `sync-artifact-stale`。该命令会把变化文件映射回来源阶段，自动把下游依赖阶段标记为 stale，把 drift 记录写入 `integrity_ledger.jsonl`，并刷新 passport 的 hash 基线。

`generate-analysis-code` 会读取已检索文献、`methods/method_requirements.json`、`methods/method_plan.md` 和 `data/data_inventory.json`，在项目 `code/` 目录下生成可审阅、可运行的 Python baseline 分析代码，并写入 `methods/analysis_code_manifest.json`。默认输出已经扩展为两张表和四张 SVG 图：数据分析流程、数据处理流程、方法分析流程、数据喂入方法后的输出流程。该阶段不是跳过科研审查的最终模型生成器，而是可复现的代码脚手架；后续仍必须用 `verify-methods` 运行生成命令、记录 `methods/run_manifest.yaml`，并确认所有声明输出都存在后才能继续写 Methods。`inventory-results` 会把通过验证的图表转成 `results/result_manifest.yaml`，`write-results` 再根据该 manifest 写出不含文献引用的结果段落。

## Paper Fetch 集成

本仓库把 [`Dictation354/paper-fetch-skill`](https://github.com/Dictation354/paper-fetch-skill) vendored 到 `third_party/paper-fetch-skill`。Adapter 会优先使用 PATH 中的 `paper-fetch` 命令；如果没有，也可以使用项目内 vendored runtime source。建议在独立虚拟环境中安装：

```powershell
python -m pip install -e third_party\paper-fetch-skill
```

该第三方 runtime 使用 MIT License，二次分发时需要保留其 license notice。

## 许可证

DraftPaper CLI 使用 MIT License。第三方组件保留其各自许可证。
