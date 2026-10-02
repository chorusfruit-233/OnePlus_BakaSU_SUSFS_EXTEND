# USB WiFi 驱动与固件内建支持

主分支 `main` 为构建矩阵中的每个机型，按它实际同步到的内核源码尽可能内建 USB 无线网卡驱动、依赖与固件。驱动和 `cfg80211/mac80211` 等依赖以 `=y` 链接进内核 Image；所选驱动可获取的固件通过 `CONFIG_EXTRA_FIRMWARE` 同样链接进 Image，启动后由内核固件加载器直接提供。

- 在 Actions 的 **Build and Release OnePlus Kernels (Built-in USB WiFi)** 中选择 `main`。`config_path` 可指定一个机型配置，留空则沿用工作流的机型矩阵。
- `profiles/usb-wifi.json` 维护 USB 网卡候选。构建使用该机型的完整 Kconfig 解析菜单、依赖和版本差异，逐个尝试内建；对厂商缺少结束引号的 `source` 行采用原生 Linux 的行尾终止规则，保持源码原样，并把兼容处理记录在覆盖报告中；源码没有的驱动、无法满足的依赖都会保留具体原因，不让单个不可用候选阻断其他可用驱动。未在该机型内核树中出现的驱动仍需后续回移。
- 保留原配置中的 `CFG80211_WEXT`、`CFG80211_WEXT_EXPORT` 和 `NL80211_TESTMODE`，避免 USB 候选改变板载 WiFi 模块依赖的结构布局。会改变这些配置的驱动或可选辅助项自动回退并记录原因，`olddefconfig` 后和编译完成后再次检查。例如原厂关闭 WEXT 时跳过 `ORINOCO_USB`；原配置已兼容时仍可内建。
- OP13 / OOS16 / 6.6.118 使用 `PJZ110_16.0.10.501(CN01)` 原厂 WiFi 模块的 ABI 参考，保存在 `profiles/vendor-wifi-abi/`。其 BTF 确认测试模式回调存在，因此启用 `NL80211_TESTMODE=y`，并保持 WEXT 关闭；不能仅从关闭 WiFi 核心的 GKI 配置推断这些厂商选项。打包前额外核对 43 个内建 `cfg80211` 符号的 CRC，缺失、变为模块或 CRC 不匹配都会停止打包；结果保存在 `usb-wifi/vendor-abi.txt`。其他系统版本仍需其原厂模块参考及真机验证。
- 固件只针对最终启用的驱动准备，从固定版本的 `linux-firmware` 和 ZD1211 官方固件包下载，记录来源、校验值和许可证。固件放入构建目录并通过内核的 [内建固件机制](https://docs.kernel.org/driver-api/firmware/built-in-fw.html) 写入 `CONFIG_EXTRA_FIRMWARE` / `CONFIG_EXTRA_FIRMWARE_DIR`；已覆盖的固件无需额外安装。
- `cfg80211` 需要外部监管数据库时同时内建 `regulatory.db`，启用签名验证时选择与该内核实际信任证书匹配的官方 `wireless-regdb` 版本和签名。没有匹配的已固定版本会列为缺失。下载采用有限重试与校验后的对象缓存，减少批量构建的重复下载。
- 个别固件缺失时会明确标记覆盖不完整，相关芯片仍可能需要设备已有固件。驱动经过 `olddefconfig` 后按实际 `=y` 的结果准备固件；下载或校验失败、没有任何可内建驱动、后续配置使已确认内建的驱动降为 `m/n`，或内建固件配置丢失都会停止构建。Image 编译完成后再次验证最终配置，并逐个检查固件原始字节和精确请求名称确实存在于本次编译的 Image 中；刷机包只使用这一已验证产物。
- 刷机包带 `_USBWiFi.zip` 后缀。包内 `usb-wifi.config.txt` 按机型和内核列出驱动覆盖、未启用原因、内建与缺失固件；`usb-wifi/plan.json`、`usb-wifi/manifest.json`、`usb-wifi/WHENCE` 与 `usb-wifi/licenses/` 保存配置计划、固件来源和许可证。Actions 摘要显示覆盖报告，debug 产物包含同一套元数据。
- 勾选 `make_release` 时发布独立的 `usb-wifi-*` 预发布版本，不替换已有的 Latest Release。默认仍只生成构建产物。
- 刷入前禁用或卸载原 `oneplus_wifi_lkm` 模块，刷入后重启。内建驱动不能用 `rmmod` 卸载，恢复普通版本需要刷回对应的普通内核。

45 项候选同时覆盖常见驱动和旧款网卡。只允许模块加载的驱动会跳过；部分驱动有上游实验限制，报告会保留说明。固件覆盖状态针对本次源码和清单识别出的需求，实际 USB 网卡绑定及工作情况仍需测试。

已在上游 arm64 `defconfig` 基础上用原生 C Kconfig 验证 5.10、5.15、6.1、6.6、6.12，分别保留 26、26、28、32、31 项内建 USB 驱动，同时保持上述 WiFi ABI 配置。此检查验证配置解析及 `olddefconfig` 的结果，尚未完成所有机型的完整内核编译和真机测试。OTG 供电、Android 网络管理，以及厂商 WiFi 模块与现有补丁的兼容性仍需逐机型验证。

本地回归检查：

```sh
python3 -m pip install --target /tmp/usb-wifi-python -r scripts/requirements-usb-wifi.txt
PYTHONPATH=/tmp/usb-wifi-python python3 -m unittest discover -s tests -v
```

## NoMount 内建支持

所有机型以及 ReSukiSU / KernelSU 两种构建默认内建 [官方 NoMount](https://github.com/maxsteeel/nomount/tree/c5fad9d8f97c5a207f7342fd91789449915ea047)。源码固定到 `profiles/nomount.json` 的提交，并验证归档 SHA256；按官方手动集成方式接入 `fs/Kconfig` / `fs/Makefile`，启用 `CONFIG_NOMOUNT=y` 和其通信所需的 `CONFIG_KEYS=y`。xattr 回调与 VFS 调用的参数根据该机型实际头文件适配，避免仅按版本号判断厂商回移接口；清单分别记录上游和适配后源码的校验值。

构建在 `olddefconfig` 后检查配置，编译后检查 `System.map` 中的初始化函数与 key type，以及本次 Image 中的初始化信息；缺失则停止打包。ZIP 和 debug 产物的 `nomount-support/` 包含提交、源码校验值、许可证和验证报告。

刷入后仍需在管理器中安装[官方 NoMount 元模块](https://github.com/maxsteeel/nomount/releases)，用于加载模块规则和提供 WebUI；内建支持无需加载 `nomount.ko`。可用元模块附带的 `nm version` 检查内核通信。已在上游 5.10、5.15、6.1、6.6、6.12 上实际编译 ARM64 NoMount 对象并检查关键符号，53 项回归测试通过；尚未完成所有机型的完整内核编译和真机测试。

同步上游更新时保留每机型配置解析、固件内建、编译后验证和 USBWiFi 产物命名。以下为上游项目说明。

---

<div align="center">

# 🔥 Huangdihd's Fork of Wild Kernels for OnePlus (Oppo/Realme)

[![KernelSU](https://img.shields.io/badge/KernelSU-Supported-green)](https://kernelsu.org/)
[![ReSukiSU](https://img.shields.io/badge/ReSukiSU-Supported-green)](https://resukisu.github.io/)
[![SUSFS](https://img.shields.io/badge/SUSFS-Integrated-orange)](https://gitlab.com/simonpunk/susfs4ksu)
[![OnePlusOSS Tracking Status](https://img.shields.io/badge/OnePlusOSS--Tracker-active-green)](https://github.com/WildKernels/OnePlus_KernelSU_SUSFS/blob/status-page/README.md)

</div>

---

## ⚠️ Disclaimer

Flashing this kernel will not void your warranty, but there is always a risk of bricking your device. Please make sure to:
- 💾 Back up your data
- 🧠 Understand the risks before proceeding

- I am **not responsible** for bricked devices, damaged hardware, or any issues that arise from using this kernel.

- **Please** do thorough research and fully understand the features added in this kernel before flashing it!

- By flashing this kernel, **YOU** are choosing to make these modifications. If something goes wrong, **do not blame me**!

<div align="center">
  
# **🚨 Proceed at your own risk!**

</div>

---

## 🔧 Available Kernels

<div align="center">

| Kernel | Repository | Status |
|--------|------------|--------|
| 🏗️ **GKI** | [GKI_KernelSU_SUSFS](https://github.com/WildKernels/GKI_KernelSU_SUSFS) | ✅ Active |
| 👑 **Sultan** | [Sultan_KernelSU_SUSFS](https://github.com/WildKernels/Sultan_KernelSU_SUSFS) | ✅ Active |
| 📱 **OnePlus/Oppo/Realme** | [OnePlus_KernelSU_SUSFS](https://github.com/WildKernels/OnePlus_KernelSU_SUSFS) | ✅ Active |
| 📱 **Samsung** | [Samsung_KernelSU_SUSFS](https://github.com/WildKernels/Samsung_KernelSU_SUSFS) | ✅ Active |
</div>

---

## 🔗 Additional Resources

- 🩹 [Kernel Patches](https://github.com/WildKernels/kernel_patches)
- ⚡ [Kernel Flasher](https://github.com/fatalcoder524/KernelFlasher)

---

## 📱 Device Compatibility

- Please verify the device compatibility before flashing here: [Compatibility_Info](https://github.com/WildKernels/OnePlus_KernelSU_SUSFS/blob/main/compatibility.md). 

---

## 📱 OnePlusOSS Repositories Tracking

- 📊 **Live Dashboard**: [OnePlus Repos Tracking & Changes](https://github.com/WildKernels/OnePlus_KernelSU_SUSFS/blob/status-page/README.md)
- ⏱️ **Update Frequency**: Every 2 hours (Automated)
---

## ✨ Features

- 🔐 **ReSukiSU**: Kernel-based Android Root Solution,forked from sukisu
- 🥷 **SUSFS**: An addon root hiding kernel patches and userspace module for KernelSU
- 🛡️ **BBG**: LSM-based Baseband Guard security to protect critical device partitions. abl/efisp can be added to whitelist for efisp exploit devices.
- 🛠️ **HMBIRD SCX**: Scheduler extensions for SM8750/MT6991 devices
- 🖧 **BBRv1**: Improved TCP congestion control
- 🖧 **BBRv3**: Improved TCP congestion control
- 🚦 **CAKE and PIE qdisc Support**: Better Net Schedulers
- ✅ **LTO**: Link Time Optimisation enabled
- 🚀 **Optimisation patches**: Memory, I/O, CPU scheduler, network and other general tunings
- 🌐 **TTL Target Support**: Network packet manipulation
- 🧱 **IP Set & IPv6 NAT Support**: Advanced firewall capabilities and IPv6 NAT Support
- ⚡️ **TMPFS XATTR / POSIX ACL**: Extended TMPFS support for meta modules and Mountify
- </> **Unicode Bypass Fix**: Prevent path traversal and other detections using non-printable Unicode codepoints [Experimental]
- 🖥️ **Droidspaces Support**: Support Portable Linux containers to run full Linux environments.
- 🔃 **NTSync**: Provide high-performance, low-latency synchronization primitives compatible with the Windows NT kernel API

---

## 📋 Installation Instructions

- **KernelSU**: Developed by [tiann](https://github.com/tiann/KernelSU).
- **ReSukiSU**: Developed by [ReSukiSU Team](https://github.com/ReSukiSU/ReSukiSU)
- **Magic-KSU**: Developed by [5ec1cff](https://github.com/5ec1cff/KernelSU).  
- **SUSFS**: Developed by [simonpunk](https://gitlab.com/simonpunk/susfs4ksu.git).
- **SUSFS Module**: Developed by [sidex15](https://github.com/sidex15).
- **Sultan Kernels**: Developed by [kerneltoast](https://github.com/kerneltoast).
For GKI installation, please follow the official guide:

📖 **[KernelSU Installation Guide](https://kernelsu.org/guide/installation.html)**

You can also find Installation instructions in the release notes.

---

## 🌟 Special Thanks

**These amazing people help make this project possible! ❤️**

<div align="center">


| 🔧 **Project** | 👨‍💻 **Developer** | 🔗 **Link** |
|:---------------:|:----------------:|:-----------:|
| **KernelSU** | tiann | [![GitHub](https://img.shields.io/badge/GitHub-tiann-blue?style=flat-square&logo=github)](https://github.com/tiann/KernelSU) |
| **ReSukiSU** | resukisu | [![GitHub](https://img.shields.io/badge/GitHub-resukisu-blue?style=flat-square&logo=github)](https://github.com/ReSukiSU/ReSukiSU) |
| **Magic-KSU** | 5ec1cff | [![GitHub](https://img.shields.io/badge/GitHub-5ec1cff-blue?style=flat-square&logo=github)](https://github.com/5ec1cff/KernelSU) |
| **SUSFS** | simonpunk | [![GitLab](https://img.shields.io/badge/GitLab-simonpunk-orange?style=flat-square&logo=gitlab)](https://gitlab.com/simonpunk/susfs4ksu.git) |
| **SUSFS Module** | sidex15 | [![GitHub](https://img.shields.io/badge/GitHub-sidex15-blue?style=flat-square&logo=github)](https://github.com/sidex15) |
| **Sultan Kernels** | kerneltoast | [![GitHub](https://img.shields.io/badge/GitHub-kerneltoast-blue?style=flat-square&logo=github)](https://github.com/kerneltoast) |
| **Baseband Guard** | vc-teahouse | [![GitHub](https://img.shields.io/badge/GitHub-vc--teahouse-blue?style=flat-square&logo=github)](https://github.com/vc-teahouse/Baseband-guard.git) |
| **Droidspaces** | ravindu644 | [![GitHub](https://img.shields.io/badge/GitHub-ravindu644-blue?style=flat-square&logo=github)](https://github.com/ravindu644/Droidspaces-OSS.git) |

</div>

*If you have contributed and are not listed here, please remind me!* 🙏

---

## 💬 Support

If you encounter any issues or need help, feel free to:
- 🐛 Open an issue in this repository
- 💬 Reach out to me directly

---

## 📱 Connect With Us

<div align="center">
  
[![Telegram](https://img.shields.io/badge/Telegram-huangdihd-blue?logo=telegram)](https://t.me/huangdihd)
[![Telegram Group](https://img.shields.io/badge/Telegram-huangdihd_wildkernel-blue?logo=telegram)](https://t.me/huangdihd_wildkernel)

</div>

---

## 💝 Donations

Any and all donations are appreciated!

PayPal: [paypal.me/fatalcoder524](https://paypal.me/fatalcoder524)

DM on Telegram for UPI donations!
