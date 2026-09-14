# v4.0 zcode / pi：明确整改

仅执行 Codex 当前交接列出的 review findings，先读 Issue、PR 最新 SHA、指定独立审阅与交接标识。确认旧写入者已停，不根据陈旧截图/聊天施工。

成立则最小必要修复并补回归；反驳要可复现证据，不能自行关闭 blocker。P0/P1 与正确性/AC/安全/兼容阻塞 P2 先处理，P3 不顺手扩大。

根因或架构边界不清就返回 Codex；同根因最多两轮有据失败后止损。逐项记录 Resolved / Unresolved / Disputed、实际验证和新的 SHA。新提交必须独立增量复核，旧 PASS 不再直接有效。

按 11 或 12 写结果并主动给返回 Codex 的短句，然后结束；不调用 reviewer、不改验收门禁、不合并。
