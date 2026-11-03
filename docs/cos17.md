# OnePlus 13 ColorOS17 实验适配

本轮目标由用户确认为 `PJZ110_17.0.0.103(CN01)` / Linux 6.6.118。在 Actions 的 **Build OnePlus 13 OOS16 / ColorOS17 (Built-in USB WiFi)** 中选择 `os_target: cos17`，或直接运行 **Experimental ColorOS 17 Kernel Build**。默认生成 `AK3_OP13_COS17_*_USBWiFi.zip` artifact，不创建 Release；通用构建入口仍默认选择 OOS16。

源码基线仍为官方已公开的 `oneplus/sm8750_b_16.0.0_oneplus_13`，GKI 为 android15-6.6。2026-11-03 核对 OnePlusOSS 的 OP13 common 与 modules/device-tree 仓库时，均没有 ColorOS17 专用分支。C17 的配置和 manifest 独立保存，HMBIRD、NTSync 沿用此源码对应的 A16 补丁，不将系统名称当作内核源码版本。

C17 跟随当前主线的 BakaSU、SUSFS v2.3.0、kernel_patches 和 BBG。Hybrid Mount 保留已验证的 `89f328fd945c72794a6505d779f6d85834d131a3` 及归档 SHA256，不恢复旧实验分支的 v6.2.3 源码。BakaSU/SUSFS 不再默认固定到 10 月 7 日的旧提交，仍可通过通用入口显式选择提交。

`profiles/vendor-wifi-abi/op13-cos17-6.6.118.json` 保存旧实验分支从 C17 `vendor_boot_b.img` 提取的原厂 `cfg80211.ko` 参考：43 个 cfg80211 导出及 7 个 rfkill 导入，cfg80211 SHA256 为 `6896d8c806e5eeb9281f7156f591ad00b8ac16cfd11121387da03aeac8a97132`。这些 CRC 与 OOS16 参考相同，但两套参考按系统标签分别匹配。

高通 WLAN 模块的完整导入尚未独立审计，参考文件保留 `factory_wlan_imports: unverified`，构建报告明确标注实验性质。通过这 50 项检查表示内建 cfg80211/rfkill 与该参考匹配，不表示已经验证 C17 的板载 WiFi、启动、USB 设备或挂载功能。OOS16 的真机验证结论只属于 OOS16。

构建在没有匹配的系统/内核 ABI 参考时直接报错，不能用 OOS16 参考补位。原有内建 USB WiFi、固件、Hybrid Mount、重复模块加载兼容及发布产物校验继续保留。上游同步后会同时保留两个明确目标，工具链镜像读取两套 manifest 并去重。

本轮验证记录将在 C17 完整构建结束后补充；尚未进行 C17 真机启动验证。
