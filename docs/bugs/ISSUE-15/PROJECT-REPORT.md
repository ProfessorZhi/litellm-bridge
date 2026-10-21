# LIT-0222 | DeepSeek Anthropic Messages `tool_removal` 422 项目报告

> 项目状态（2026-10-21 核查）：**功能 E2E PASS / G5 工程验收 HOLD / 生产未部署**  
> 代码候选：`841fa33f40d3938a3dfde2078b25fcbfb97f8e40`；正式 Work Item：`LIT-0222`  
> 本报告是脱敏的阶段交付记录，不代表合并批准、发布批准或 Yale 原始请求的逐字节重放。

## 1. 需求及验收边界

东京共享网关的 `v4pro` 模型组经 LiteLLM DeepSeek Anthropic Messages 适配路径调用真实 DeepSeek。Claude Code 会话中途添加工具，再撤销它们时，DeepSeek 因不支持 `tool_removal` 内容块返回 HTTP 422。目标是仅修复 DeepSeek 的转换层，保留既有 `tool_definition` 兼容补丁和无关消息，不修改其他 Provider、数据库或生产部署。

验收要求依次为：G0 现场盘点、G1 RED 复现、G2 GREEN 修复、G3 回归测试、G4 **真实 DeepSeek E2E A/B**、G5 独立审核和发布前审计。功能通过不等于 G5 或线上修复完成。

需求来源：[Issue #15](https://github.com/ProfessorZhi/litellm-bridge/issues/15)；旧补丁：[Issue #13](https://github.com/ProfessorZhi/litellm-bridge/issues/13) / [PR #14](https://github.com/ProfessorZhi/litellm-bridge/pull/14)。本修复 [PR #16](https://github.com/ProfessorZhi/litellm-bridge/pull/16) **stacked on PR #14 的 head**，不独立包含旧补丁变更。

## 2. 原事故证据及根因

2026-10-20 02:12:55–57 UTC 两次失败请求均在受控加密 Edge 归档中找到。原始请求结构核查（未复制任何客户正文、工具名、鉴权信息到仓库）：

| 指标 | 实测 |
| --- | --- |
| 完整入站 HTTP Body | 两次分别为 1,982,814 / 1,982,794 bytes，未截断 |
| 历史消息 / 顶层工具 | 1,017 条 / 147 个 |
| `messages[233]` | 根级 `system` 消息，3 个 `tool_addition.tool.tool_definition` |
| `messages[1016]` | 根级 `system` 消息，1 个 `text` + 3 个 `tool_removal.tool_reference` |
| 工具调用历史 | 281 对 `tool_use` / `tool_result`，无悬空；被撤销的 3 个工具此前调用次数均为 0 |
| 请求控制 | `stream=true`、`max_tokens=32000`、`model=v4pro`；自适应 thinking、context_management、output_config、顶层 system、9 个 Anthropic beta 标识 |
| 原始上游错误 | `messages[1016].content: unknown variant tool_removal`，HTTP 422 |

根因不是上下文长度、模型额度或用户误用工具：原 DeepSeek 转换器会透传不支持的 `tool_removal`；第一次修复仅删除 removal 后，历史 `tool_addition.tool_reference` 又引用了从最终 `tools[]` 删除的工具，导致真实 DeepSeek 返回 HTTP 400（`messages.233.content.0: tool_addition references unknown tool`）。

## 3. 修复设计及代码范围

在 `litellm/llms/deepseek/messages/transformation.py` 中使用两阶段转换：

1. 第一遍按消息顺序验证工具声明、撤销和重新添加，计算**会话末尾仍处于撤销状态**的工具名。
2. 第二遍去掉这些名字对应的历史 `tool_addition` 与 `tool_removal` 协议块；保留内部声明账本以验证撤销合法性；如系统消息因此为空则删除该消息。
3. 构建最终 DeepSeek `tools[]`，不包含已撤销工具；保留无关文本、历史 `tool_use` / `tool_result`、thinking 和其他可保留内容。
4. 对未声明名称、错误位置、格式错误、无法解析的 MCP 引用等无法安全转换的形状，使用明确的本地 400（fail-closed），不向 DeepSeek 透传非法内容。

相对旧 PR #14 的基线，业务转换模块变更 **+178 / -34 行**，对应测试 **+356 / -13 行**；原先的技术说明见 [README.md](README.md)。修复代码是两个独立提交：`67bd6b5c`（首次处理 removal）及 `841fa33f`（补历史 addition 两阶段处理）。

## 4. RED → GREEN → E2E 的真实执行记录

| Work Engine Run | 真实测试类型 | 关键结果 |
| --- | --- | --- |
| `RUN-0006` | 短合成请求，真实 DeepSeek | A=422 / B=200；不能当作长会话验收 |
| `RUN-0007` | 1,017 消息匿名长历史，非流式 | A=422 / **B=400，Run FAILED**；由此发现历史 addition 引用问题 |
| `RUN-0008` | 两阶段候选，匿名长历史流式、`max_tokens=16` | A=422 / B=200，SSE `message_stop`；Run SUCCEEDED |
| `RUN-0009` | 两份**原始控制参数对齐**的匿名长历史，真实 DeepSeek，`stream=true`、`max_tokens=32000` | A2/A1 均 422；**B2/B1 均 200**，SSE 均完整结束、`stop_reason=end_turn`，无 `error` 事件；Run SUCCEEDED |
| `RUN-0010` | 独立 G5 QA | **Run FAILED，含义为发布门禁 HOLD**，不是功能代码失败；G5 Activity 仍 PENDING |

`RUN-0009` 的两份测试请求分别为 1,982,794 与 1,982,814 bytes，均包含 1,017 条消息和 147 个工具，保留 `messages[233]` 添加与 `messages[1016]` 撤销的位置、`thinking=adaptive` / `adaptive+display`、顶层 system 的缓存结构、上下文管理、9 个 beta 标识，以及所需的工具调用历史形状。所有消息正文、工具名、用户身份及工具返回值均为**合成数据**。

在最后的真实 A/B 中，同一合成 fixture 在 A、B 两路请求字节及请求控制参数相同。B2 流式 usage：910,506 input、214 output；B1：42 input、910,464 cache-read、379 output；估算本轮四次真实上游请求合计约 US$1.24。两个 B 请求均返回 `message_stop`。

重要限制：**并未重新发送 Yale 的原始 1.98 MB 私人会话**。原事故 DeepSeek parser 报错列号为 2,215,035，合成请求列号不同；可以确认同一协议路径/错误变体及修复效果，不声称原始报文逐字节一致。历史真实工具调用数为 281 对，现有合成用例不逐条复制其全部分布。

## 5. 自动化检查与独立审查

- 本地 `pytest tests/test_litellm/llms/deepseek/`：**119 passed**（最终提交之后的证据见 `RUN-0009`）。
- `ruff check`、`ruff format --check`、`git diff --check`：通过；候选工作树 clean。
- Anthropic pass-through 扩展套件曾记录 249 passed / 16 failed，16 个失败在旧基线亦出现；这不是整仓 full CI 通过的证明。
- 最新 PR head 的 GitHub Actions 三个 check（两个 PR-title、一个 unit-test）均在**没有分配 runner / 没有执行步骤**时失败。平台给出的原因是账户付款失败或 Actions spending limit；因此正式 CI 状态为 **NOT_RUN / blocked by billing**，而非代码测试失败。
- 独立代码审查未发现高风险 blocker；已识别残余测试边界：撤销→重加→再撤销、最终撤销但历史定义与顶层同名且 contract 冲突的情况。

## 6. G5 HOLD：尚未关闭的交付阻断

1. **证据可复核性**：重新检查 80 条原登记证据，78 条匹配、2 条因指向可变工作树文件和追加式 Mock 日志而 SHA 漂移。原 SHA 对应的源码快照及 Mock 前 3 行已在东京 `LIT-0222/evidence-repair/` 中冻结恢复，但 Work Engine 旧 locator **尚未获批准 repoint 或签署 waiver**。随后 G5 `RUN-0010` 另增两条自身匹配的证据，总数 82。
2. **正式 CI**：GitHub Actions billing/spending 障碍需 Owner 处理后复跑；或者有明确、留痕的基础设施豁免决定。
3. **记录落地主线**：[hwz-records Draft PR #23](https://github.com/ProfessorZhi/hwz-records/pull/23) 已更新项目 Brief/Plan/Verify，但尚未合并；默认 records root 仍缺该 Item 卡片。
4. **独立 G5 复核**：`RUN-0010` 判定 HOLD，`g5-review=PENDING`，`LIT-0222` 仍 `ACTIVE`、`outcome=null`。没有合并、生产发布或最终交付许可。

## 7. 协议折衷及部署边界

- DeepSeek 缺乏 Anthropic 的位置化动态工具变更语义。本修复将其降级为当前最终可用工具集；对于最终撤销的工具，历史 addition 会被省略，可能改变 Prompt Cache 命中及历史工具声明的可见性。不是无损的全协议转换。
- 本次隔离 Mock 观察到现有 LiteLLM 转发时过滤了入站 `anthropic-beta`、将 `thinking=adaptive` 转为 `enabled/budget_tokens=4096`，并去掉 `output_config.effort`；这些是 A/B 两组共有行为，非此补丁新增，需在独立兼容审计中处理。
- PR #16 仅为 **Draft**，依赖先合入旧 PR #14；后续需要在保留旧 `tool_definition` 补丁的前提下合并、做金丝雀和线上 E2E。
- 截至本报告，生产 `litellm-shared-litellm` 的有效转换模块 SHA-256 为 `26bf97ca7148ed4a671990f4802318590dbf33feadd1f5fd7b900705655ba15e`，不含 `tool_removal` 逻辑；候选模块为 `021a29f8914d763a89406ef3cd97f85d894114a9248fa03c9b1d6f69ba161ef2`，**未部署**。
- 发布前需保存现有生产镜像 `sha256:6946bc15...` 与 Compose/配置快照，建立可回退的镜像替换及健康验证流程。Git revert 只影响源码，不能代替生产镜像回滚。

## 8. 交付物与权限说明

- 正式 Work Item：`LIT-0222`（Tokyo Work Engine，10 个 Run）
- 代码：[Bridge PR #16](https://github.com/ProfessorZhi/litellm-bridge/pull/16)，当前 head `841fa33f40`，Draft
- 原生 G4 实证：`LIT-0222/RUN-0007`（失败）、`RUN-0008` 和 `RUN-0009`（通过）
- 独立 QA：`LIT-0222/RUN-0010/QA-REVIEW.md`（G5 HOLD）
- 稳定项目档案：[Records PR #23](https://github.com/ProfessorZhi/hwz-records/pull/23)
- 需求和执行历史：[Issue #15](https://github.com/ProfessorZhi/litellm-bridge/issues/15)

执行证据原件保留于东京受控 artifacts / 加密归档；GitHub 仅存脱敏统计、技术实现、哈希和可审阅报告，不包含客户正文、原始 HTTP Body、鉴权头或生产密钥。
