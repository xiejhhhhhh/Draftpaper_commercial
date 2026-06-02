# DraftPaper CLI

`AI科研工作流` `本地优先` `Python CLI` `LaTeX初稿` `文献证据链` `全文抓取` `Codex Skill Wrapper`

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

```powershell
python -m pip install -e .
python -m draftpaper_cli.cli create-project --root C:\DraftPaper_CLI\projects --idea "你的研究idea" --field "machine learning astronomy" --target-journal APJS
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\your_project --query "topic keywords"
python -m draftpaper_cli.cli validate-project --project C:\DraftPaper_CLI\projects\your_project
```

运行测试：

```powershell
python -m unittest discover -s tests
```

## Paper Fetch 集成

本仓库把 [`Dictation354/paper-fetch-skill`](https://github.com/Dictation354/paper-fetch-skill) vendored 到 `third_party/paper-fetch-skill`。Adapter 会优先使用 PATH 中的 `paper-fetch` 命令；如果没有，也可以使用项目内 vendored runtime source。建议在独立虚拟环境中安装：

```powershell
python -m pip install -e third_party\paper-fetch-skill
```

该第三方 runtime 使用 MIT License，二次分发时需要保留其 license notice。

## 许可证

DraftPaper CLI 使用 MIT License。第三方组件保留其各自许可证。
