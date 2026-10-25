截至 2026-10-25，本次已同步 WildKernels 上游到 `ce52f331beea06a0c693ec58cb1b62a08446f5ac`，保留真实合并历史。合入 SUSFS 2.3.0 支持、GitLab API 归档下载及逐次降低连接数的重试逻辑。项目仍只维护 OP13 / OOS16 / Android 15 / 6.6.118；未引入上游新增的其他机型。

本次固定依赖的处理结果：

| 依赖 | 当前版本或提交 | 处理 |
| --- | --- | --- |
| Hybrid Mount VFS | `89f328fd945c72794a6505d779f6d85834d131a3` | 更新源码及归档 SHA256；保留 `hybridmount` / `hm1` 协议 |
| linux-firmware | `20261019` / `a2dcb924f0897368b0b4f305cbf9808cdda90ce0` | 更新稳定发布、Git 根树与 WHENCE 校验值 |
| wireless-regdb | `2026.09.03` | 已是最新发布；保留 `2023.09.01` 以匹配旧内核信任证书 |
| ZD1211 firmware | `1.5` | 已是最新发布，保留固定归档和 SHA256 |
| kconfiglib | `14.1.0` | 已是 PyPI 最新版本 |
| actions/checkout | `v7.0.1` | 更新 |
| actions/cache | `v6.1.0` | 更新 |
| actions/setup-python | `v7.1.0` | 更新；测试解释器仍使用 Python 3.12 |
| actions/github-script | `v9.0.0` | 更新；已核对 Node 24 和现有脚本用法 |
| actions/upload-artifact | `v7.0.2` | 统一最终产物与共享中间产物版本 |
| actions/download-artifact | `v8.0.2` | 与上传端统一 |
| anomalyco/opencode/github | `v1.19.4` | 从 `latest` 改为明确发布版本，后续由 Dependabot 跟进；其内部 CLI 仍由该 Action 自行安装 |

以下源码已经在每次构建时解析或下载所选分支，核对时的上游提交如下。它们不会因为本次审计而改成固定快照，用户指定的分支或提交仍然生效。

| 依赖 | 跟踪分支 | 本次核对的提交 |
| --- | --- | --- |
| Baka-SU/BakaSU | `main` | `d5e9e025b8b49155f8014684d64c91742b465f65` |
| tiann/KernelSU | `main` | `528bafc5696196f3a9500cee2e7e18497421cd32` |
| simonpunk/susfs4ksu | `gki-android15-6.6` | `c51cd8aad3f7e2f8c48bc3bda88cc68cf7d82895`（v2.3.0） |
| WildKernels/kernel_patches | `main` | `159a8f3b93af582b07d0d44bfa7d08b96d667ec0` |
| vc-teahouse/Baseband-guard | `main` | `a54e0dc6cf0aff4dd87fec49644a02d2eb612905` |
| huangdihd/AnyKernel3 | `gki-2.0` | `ea531d03965f702a45e1b0ab7c5db8d196c975c3` |
| OnePlusOSS common kernel | `oneplus/sm8750_b_16.0.0_oneplus_13` | `e1b346b6b4f4096eb342ae3684838a942fd6f6c4` |
| OnePlusOSS modules/device tree | `oneplus/sm8750_b_16.0.0_oneplus_13` | `d50b305f7da9e14715a25120a4ac7b1a4b8b97c3` |

Droidspaces、NTSync、调度及优化补丁通过 `kernel_patches` 跟进，本次核对的 OP13 活跃分支所引用补丁均存在。AnyKernel3 已移出静态工具链缓存，每次构建直接同步分支，避免 `AnyKernel3-gki-2.0.tar.gz` 的旧缓存遮蔽上游更新。SUSFS 仍按构建开始时解析的提交统一下载一次并供矩阵复用；本次同时适配新的 API URL 与旧归档 URL。

以下版本继续保持兼容约束：

- OnePlus `kernel-build-tools`：`434f141b6d22a773a163fa9c707b19b4d254d989`；Android Clang 预编译工具：`b099698c583b8361ca771f3cc8d6af6f729f39b3`。两者仍与最新官方 OP13 manifest 一致，未用 CodeLinaro 通用分支的其他提交替换。
- 默认 ZyC Clang：`19.0.0git-20240723-release`。仓库按发布时间的 `latest` 实际为 Clang 14，直接跟随会降级；最高版本 Clang 23 为开发构建。本次保持已验证工具链，未将开发构建直接用于发布。
- 原厂无线 ABI 参考仍限定 `PJZ110_16.0.10.501(CN01)` / 6.6.118。其 CRC 与结构布局来自原厂模块，系统更新后需要对应原厂模块重新建立参考。
- 当前配置关闭 Rust 构建，未启用新的 Rust、bindgen 或其他机型专用依赖。

`.github/dependabot.yml` 每周跟进工作流、构建 composite action 的 GitHub Actions 依赖和 `scripts/requirements-usb-wifi.txt`。WildKernels 上游同步可通过 `opencode` 工作流留空 prompt 手动触发；原有 schedule 处于注释状态，本次保持现有触发频率。固件和 Hybrid Mount 使用经过校验的固定快照，更新时需要同步校验值、协议兼容检查及实际内核验证。

上游自动合并保留两亲历史，在旧 sanitizer 后执行 `scripts/maintain_target.py`：先验证维护目标，再清除恢复的其他机型并校正 BakaSU 命名。无需 agent 的快速 PR 路径也会只读校验这些约束。传给维护 agent 的旧指令会适配当前品牌及单目标要求，用户原始请求和 `.github/opencode/` 内文件保持原样。

本地 Ubuntu 开发环境的 requests 从 2.32.5 更新为 2.34.2；PyYAML 6.0.3、kconfiglib 14.1.0 已为最新。构建源码同步脚本未使用的 requests 导入已删除，避免 CI 引入隐式依赖。

新版 Hybrid Mount 已在真实 OP13 6.6.118 源码上完成 GKI 配置与单对象编译，确认 `hybridmount_init`、`hm_key_type` 符号存在。新固件版本经真实 Kconfig → olddefconfig → 固件准备 → olddefconfig → verify 流程，保留 32 项内建驱动、67 个固件文件，WEXT / NL80211 配置保持原厂 ABI 约束。与旧版本对照，已覆盖固件及 25 项未覆盖请求均未变化，覆盖仍为 `partial`。

主机与 Ubuntu 容器的 91 项仓库回归测试全部通过；工作流 YAML、87 个 Bash 块、内嵌 Python、Action 输入参数与 ARM64 工具链检查通过。尚未构建完整内核 Image，也未执行编译产物的厂商模块 ABI 或真机启动验证。
