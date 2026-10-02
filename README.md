# USB WiFi 内建支持

主分支 `main` 将原 `OnePlus_KSU_WIFI` 的 USB 无线网卡驱动方案整合到本仓库的内核构建中。驱动与 `cfg80211/mac80211` 等依赖以 `=y` 链接进同一个内核 Image，不再安装独立 WiFi KernelSU 模块或调用 `ksud insmod`。

- 在 Actions 的 **Build and Release OnePlus Kernels (Built-in USB WiFi)** 中选择 `main`。首次建议指定 `config_path=configs/oos16/OP13.json` 验证单设备，再扩大构建范围。
- 构建始终启用内建 USB WiFi。`profiles/usb-wifi.json` 维护驱动与依赖清单：移植原项目的 USB 驱动候选，并为 rtw88 指定实际 USB 芯片驱动。只使用对应内核树已有的代码，不引入外部驱动或跨版本移植。
- `gki_defconfig` 生成后应用配置，经过 `olddefconfig` 再严格验证。源码中没有的候选会列出并跳过；已请求的驱动或依赖若仍为 `m/n`，以及没有任何可用驱动时，会直接停止构建。
- 刷机包带 `_USBWiFi.zip` 后缀，包内 `usb-wifi.config.txt` 列出最终启用项和源码缺少的候选。相同信息也显示在 Actions 摘要中。
- 勾选 `make_release` 时发布独立的 `usb-wifi-*` 预发布版本，不替换已有的 Latest Release。默认仍只生成构建产物。
- 刷入内建 USB WiFi 内核前，禁用或卸载原 `oneplus_wifi_lkm` 模块，刷入后重启。内建驱动不能用 `rmmod` 卸载，恢复普通版本需要刷回对应的普通内核。
- 内建驱动不等于内建固件：固件仍由设备固件搜索路径提供；本仓库不下载或打包固件。USB 芯片支持、OTG 供电和 Android 网络管理能力仍需真机验证。
- 无线核心内建会改变内核配置，厂商 WiFi 模块与现有补丁的兼容性仍需验证；不要把消除独立 USB 驱动加载步骤理解为整机兼容性已经通过测试。

本地回归检查：`python3 -m unittest discover -s tests -v`。同步上游更新时保留配置应用、最终验证和 USBWiFi 产物命名。以下为上游项目说明。

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

