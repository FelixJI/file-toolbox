# ZCode：按review精确整改

读取当前PR最新head SHA、Issue合同、独立review和未解决finding。确认当前分支未被另一Agent改动，基于真实最新代码修复，不重做整个任务。

逐条判断finding，成立则最小必要修复并补相应回归证据；P0/P1和阻塞P2先处理，非阻塞P2/P3有理由移follow-up。反驳finding必须给可复现反证并交独立reviewer确认，作者不能自行抹去blocker。

只修review要求，不借机重构。普通实现自行决定；根因/架构/数据边界超出明确施工能力则交Codex。相同根因最多2轮失败后止损。

重新执行适用验证，更新Resolved/Unresolved/Disputed findings、测试、当前head/base SHA，状态回REVIEW。新提交使旧审阅过期，必须请求独立增量复核，不能拿旧PASS自行合并。

调用reviewer不可用时输出HANDOFF_REQUIRED，附准确下一动作；不假装自动完成复核。风险/验收不能因为修复赶进度而降低。
