# OnePlus 13 ColorOS17 实验适配

本轮目标由用户确认为 `PJZ110_17.0.0.103(CN01)` / Linux 6.6.118。在 Actions 的 **Build OnePlus 13 OOS16 / ColorOS17 (Built-in USB WiFi)** 中选择 `os_target: cos17`，或直接运行 **Experimental ColorOS 17 Kernel Build**。默认生成 `AK3_OP13_COS17_*_USBWiFi.zip` artifact，不创建 Release；通用构建入口仍默认选择 OOS16。

源码基线仍为官方已公开的 `oneplus/sm8750_b_16.0.0_oneplus_13`，GKI 为 android15-6.6。2026-11-03 核对 OnePlusOSS 的 SM8750 common、vendor kernel、modules/device-tree 及官方 manifest 时，均没有 OP13 的 ColorOS17 专用分支或 manifest。C17 的配置和 manifest 独立保存，HMBIRD、NTSync 沿用此源码对应的 A16 补丁，不将系统名称当作内核源码版本。

C17 跟随当前主线的 BakaSU、SUSFS v2.3.0、kernel_patches 和 BBG。Hybrid Mount 保留已验证的 `89f328fd945c72794a6505d779f6d85834d131a3` 及归档 SHA256，不恢复旧实验分支的 v6.2.3 源码。BakaSU/SUSFS 不再默认固定到 10 月 7 日的旧提交，仍可通过通用入口显式选择提交。

`profiles/vendor-wifi-abi/op13-cos17-6.6.118.json` 保存旧实验分支从 C17 `vendor_boot_b.img` 提取的原厂 `cfg80211.ko` 参考：43 个 cfg80211 导出及 7 个 rfkill 导入，cfg80211 SHA256 为 `6896d8c806e5eeb9281f7156f591ad00b8ac16cfd11121387da03aeac8a97132`。这些 CRC 与 OOS16 参考相同，但两套参考按系统标签分别匹配。

高通 WLAN 模块的完整导入尚未独立审计，参考文件保留 `factory_wlan_imports: unverified`，构建报告明确标注实验性质。通过这 50 项检查表示内建 cfg80211/rfkill 与该参考匹配，不表示已经验证 C17 的板载 WiFi、启动、USB 设备或挂载功能。OOS16 的真机验证结论只属于 OOS16。

构建在没有匹配的系统/内核 ABI 参考时直接报错，不能用 OOS16 参考补位。原有内建 USB WiFi、固件、Hybrid Mount、重复模块加载兼容及发布产物校验继续保留。上游同步后会同时保留两个明确目标，工具链镜像读取两套 manifest 并去重。

本轮已通过 110 项回归测试，包括双目标独立生成、错误目标拒绝、C17 配置缺失时禁止部分修改、未知内核 ABI 拒绝和 C17 产物标签检查。工作流 YAML、嵌入的 Bash/Python，以及 C17 独立入口和通用构建器的参数一致性检查通过。

在临时目录执行原有 sanitizer 和维护脚本后，两套目标均保留，其他机型被移除；实际执行工具链镜像的两个矩阵生成步骤，确认两套目标合并为两份固定工具链下载。受保护的 `.github/opencode/` 文件保持原样。

[本轮 C17 完整构建与产物验证](https://github.com/chorusfruit-233/OnePlus_BakaSU_SUSFS_EXTEND/actions/runs/41737681933)已通过。实际构建为 BakaSU 35257 / SUSFS v2.3.0 / Linux 6.6.118，验证了 32 个内建 USB WiFi 驱动、67 个固件的 Image 内容、50 项 C17 cfg80211/rfkill 参考 CRC，以及 Hybrid Mount 的 System.map/Image 链接。

随后实际下载原始矩阵和刷机 ZIP，通过目标标签、非空 Image/anykernel.sh、ZIP CRC、C17 实验范围说明及 Hybrid Mount 源码提交检查，并确认发布产物校验位于创建标签之前。验证过程中没有创建 Release。

产物：`AK3_OP13_COS17_android15-6.6.118_BakaSU_35257_SuSFS_v2.3.0_USBWiFi.zip`。

| 文件 | SHA256 |
| --- | --- |
| Image | `ea8572d62795a6726669e66d67aa1b352e13f4449ec7fab2d928e3dc44ddedda` |
| 刷机 ZIP | `f34f5d78ba6105a0c1f9b0b7a24c6a141d5f3a60a915b13d6857c8e1bd15d38b` |

构建覆盖生产合并 `b545365` 的代码；验证提交 `5285c1a` 仅额外加入临时验证工作流，该工作流不合入正式分支。后续仅更新文档记录。本轮同步 `main` 与原有 `work/cos17-pinned-bakasu-hybridmount-623` 分支，新构建推荐使用 `main` 的 C17 入口。

尚未进行 C17 真机启动验证，也未完成高通 WLAN 模块的独立导入审计。
