# 运行产物、Git 与 CI

## 根因，而不只是一个文件名

BOOTSTRAP_RESULT.md 是安装/沟通过程证据，持续追加它会产生新的 commit SHA，触发 PR synchronize 与新一轮检查。
ready、enabled、CLI 路径、后台存活、能力探测、当前 baseline 不应每次写回共享 project.json；这些是本机状态。
本包把上述字段移入 ignored local.json，把报告与日志移入 runtime。项目验证命令、规则、脚本仍提交。

## 三道检查

1. ignore 防止正常 git add 把新产物加入。它不解决历史已跟踪文件。
2. hygiene.py --staged 在本地提交前阻断新增/修改/重命名的产物，允许删除旧产物；业务 runner 自身也检查 COMMIT 的每个路径。
3. hygiene.py --pre-push 检查拟推送 tip 与本次引入的提交，不只检查最后 diff。先加报告再删报告，报告仍在历史里，应在未公开分支整理本次提交，不能用最后 diff 为空蒙混。

hooks 只作为本机协作守卫，可以被 --no-verify 绕过，绝不是服务器强制安全门禁或通用 secret scanner。
现有 hook manager 保留，按 BOOTSTRAP 整合；服务器要强制拦截，另在可信 CI 中集成 guard，不能把个人模型登录放入公开 CI。

## 一次迁移

```text
python .ai-flow/scripts/hygiene.py --tracked
python .ai-flow/scripts/hygiene.py --migrate
python .ai-flow/scripts/hygiene.py --migrate --apply
```

备份实际工作区内容后精确取消跟踪；不删除用户其它 Markdown。迁移后用 git diff --cached 确认只删除本地证据文件，不删除工作流源码。
已公开的历史不会被这个工具抹去；若曾推送真实密钥，需要单独撤销凭据和处理历史，不在升级中擅自 force-push。

## 少触发 CI，不等于放宽 CI

优先减少 push：在本地完成一个语义任务的实现、测试、审阅/整改后再推；checkpoint 在本地保存，不每步都提交/推送。
仅进度变化使用同一 Issue/PR 的简短状态更新，不另造“报告 PR”。这通常避免标准 push/pull_request 的 synchronize，但仓库自定义 issue_comment 自动化仍按自身触发规则运行。

本包默认不修改任何 .github/workflows 或 required checks；删除多余报告提交后，合法源码 PR 仍跑已有验证。
不要一刀切 paths-ignore: .ai-flow/**：本目录有 Python 调度器、schemas、权限规则，修改它们需要测试。
不要用 [skip ci] 或对整个必需 workflow 设置 paths-ignore；GitHub 文档说明这可能让 required check 永久 Pending，阻塞合并。[N4]

## 后续有明确授权时的 CI 分层方法（不是本包已部署的改动）

保留始终产生结果的 plan 和 required 汇总。plan 用真实 base/head 文件差异做分类，结果缺失/失败时 fail closed。
纯非执行说明：必要 Markdown/链接/产物检查。
工作流源码或规则：Python 编译、native/runner/hygiene/升级测试、需要的安全审阅，不必无依据打包所有业务二进制。
业务源码/依赖/构建配置/未知路径：原有必需业务测试/构建；未知变化默认进入重验证，而不是默认为 docs-only。
混合变化取验证集合的并集。required 汇总必须验证该跑的任务确实成功；skipped 不能替代应跑的工作。
分类脚本、CI、依赖锁、AGENTS 等自身变更须按信任边界评估，不能由 PR 作者随意改成“免检”给自己放行。
只有核验现有 required 名称、事件语义、矩阵与分支保护后才能改；不新增重复工作流来“优化”现有 CI。

FelixJI/file-toolbox 已存在 plan → prepare/shard → required 结构及 PR concurrency cancel-in-progress。
后续优化应沿用它的 scripts/automation.py ci 规划层，而不是再叠一套 parallel CI。本包仅提供迁移指引，未改该仓库的 workflow。
