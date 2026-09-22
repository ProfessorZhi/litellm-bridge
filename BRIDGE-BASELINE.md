# BRIDGE-BASELINE · 本仓定位，以及 `main` / `dev` 的性质

**一句话：本仓不是开发主线。`main` 与 `dev` 是 2026-09-04 冻结的独立历史镜像锚点，
不要在此开发，不要从此部署。**

团队仓（开发主线）：<https://github.com/79JaX/litellm-fjd>

本仓 `ProfessorZhi/litellm-bridge` 的定位是团队仓的**镜像 / 发布仓**。除 `main` / `dev`
之外的绝大多数分支都是**团队血统**（与团队历史共享、同一 SHA）。

## `main` / `dev` 是什么

| 项 | 值 |
|---|---|
| 来源 | 团队 `dev @ b2c8c24ebc` 的**树快照** |
| 内容 | 与 `fjd/dev @ b2c8c24` 的树**逐字节相同**（`git diff --quiet` 通过） |
| 历史 | **自有血统，与团队历史无共同祖先**（`merge-base` 为空） |
| 冻结 | `main` = `788ff7e588`（2026-09-04）；`dev` = 该基线 + 3 个只改 1 个文件的提交 `61b7c801c9`（2026-09-08） |

本仓属于这条自有血统的提交**只有两个**：`788ff7e588`（`main`）、`61b7c801c9`（`dev`）。
其余分支，包括 `latest/merge-all-fix`、`update/100-dev`、各 `fix/*`、各 `feature/*`，都是**团队血统**。

## 为什么不要从 `main` 部署

`main` 是冻结快照，不跟随团队修复。已实测的一例：

```text
litellm/responses/litellm_completion_transformation/transformation.py
  main           6b1ca3564e   ← 无修复（工具调用历史顺序缺陷）
  fjd/main       f39df38d06   ← 有修复
```

从本仓 `main` 构建或部署，会拿到**修复前**的代码。部署请用团队分支：本仓与团队仓
同名的团队血统分支即同一 SHA，例如 `latest/merge-all-fix`。

## 要改代码去哪

去团队仓 `79JaX/litellm-fjd` 的分支上开发。本仓只做镜像 / 发布；本仓的团队血统分支
若落后于团队，用**快进**对齐（fast-forward，**不 force**）。

## 当前对齐状态（2026-09-22）

- `latest/merge-all-fix` 已快进到团队 tip `2d57903442`（原 `86e98cb8c1`，只带
  `Dockerfile` + `ca.crt` 两个文件）。
- 同名分支里 `main` / `dev` 是**两条血统各占一个同名分支**，不是「落后几个提交」。
  按「落后」去 fast-forward 会出事。
- 完整测量见本机证据目录 `artifacts/litellm-bridge-fjd-alignment-20260922/ALIGNMENT-MAP.md`
  （证据不入仓）。
