# OnePlus 13 OOS16 内核（USB WiFi / NoMount 内建）

主分支 `main` 只维护 OnePlus 13 OOS16，唯一配置为 `configs/oos16/OP13.json`，唯一源码 manifest 为 `manifests/oos16/oneplus_13_w.xml`（OnePlusOSS 分支 `oneplus/sm8750_b_16.0.0_oneplus_13`，android15-6.6，目前已验证 6.6.118）。按该源码尽可能内建 USB 无线网卡驱动、依赖与固件。驱动和 `cfg80211/mac80211` 等依赖以 `=y` 链接进内核 Image；所选驱动可获取的固件通过 `CONFIG_EXTRA_FIRMWARE` 同样链接进 Image，启动后由内核固件加载器直接提供。

- 在 Actions 的 **Build OnePlus 13 OOS16 (Built-in USB WiFi)** 中选择 `main`。构建目标固定，不再提供机型、系统版本或配置路径选择。工具链镜像和构建 action 同样限制为这一目标；已移除其他机型、OOS14/OOS15 和 OP13 旧 6.6.89 的配置及 manifest。
- `profiles/usb-wifi.json` 维护 USB 网卡候选。构建使用该机型的完整 Kconfig 解析菜单、依赖和版本差异，逐个尝试内建；对厂商缺少结束引号的 `source` 行采用原生 Linux 的行尾终止规则，保持源码原样，并把兼容处理记录在覆盖报告中；源码没有的驱动、无法满足的依赖都会保留具体原因，不让单个不可用候选阻断其他可用驱动。未在该机型内核树中出现的驱动仍需后续回移。
- 保留原配置中的 `CFG80211_WEXT`、`CFG80211_WEXT_EXPORT` 和 `NL80211_TESTMODE`，避免 USB 候选改变板载 WiFi 模块依赖的结构布局。会改变这些配置的驱动或可选辅助项自动回退并记录原因，`olddefconfig` 后和编译完成后再次检查。例如原厂关闭 WEXT 时跳过 `ORINOCO_USB`；原配置已兼容时仍可内建。
- OP13 / OOS16 / 6.6.118 使用 `PJZ110_16.0.10.501(CN01)` 原厂 WiFi 模块的 ABI 参考，保存在 `profiles/vendor-wifi-abi/`。其 BTF 确认测试模式回调存在，因此启用 `NL80211_TESTMODE=y`，并保持 WEXT 关闭；不能仅从关闭 WiFi 核心的 GKI 配置推断这些厂商选项。打包前额外核对 50 个内建无线符号（43 个 `cfg80211`、7 个 `rfkill`）的 CRC，缺失、变为模块或 CRC 不匹配都会停止打包；结果保存在 `usb-wifi/vendor-abi.txt`。针对该版本，已内建的 `cfg80211`/`rfkill` 再次被厂商 modprobe 请求加载时返回“已加载”，避免重复符号错误中止高通驱动依赖链；仅此已建立 ABI 参考的目标启用此兼容处理，已由用户在 OP13 真机确认重启后的板载 WiFi 正常。后续系统更新仍需匹配的原厂模块参考及验证。
- 固件只针对最终启用的驱动准备，从固定版本的 `linux-firmware` 和 ZD1211 官方固件包下载，记录来源、校验值和许可证。固件放入构建目录并通过内核的 [内建固件机制](https://docs.kernel.org/driver-api/firmware/built-in-fw.html) 写入 `CONFIG_EXTRA_FIRMWARE` / `CONFIG_EXTRA_FIRMWARE_DIR`；已覆盖的固件无需额外安装。
- `cfg80211` 需要外部监管数据库时同时内建 `regulatory.db`，启用签名验证时选择与该内核实际信任证书匹配的官方 `wireless-regdb` 版本和签名。没有匹配的已固定版本会列为缺失。下载采用有限重试与校验后的对象缓存，减少批量构建的重复下载。
- 个别固件缺失时会明确标记覆盖不完整，相关芯片仍可能需要设备已有固件。驱动经过 `olddefconfig` 后按实际 `=y` 的结果准备固件；下载或校验失败、没有任何可内建驱动、后续配置使已确认内建的驱动降为 `m/n`，或内建固件配置丢失都会停止构建。Image 编译完成后再次验证最终配置，并逐个检查固件原始字节和精确请求名称确实存在于本次编译的 Image 中；刷机包只使用这一已验证产物。
- 刷机包带 `_USBWiFi.zip` 后缀。包内 `usb-wifi.config.txt` 按机型和内核列出驱动覆盖、未启用原因、内建与缺失固件；`usb-wifi/plan.json`、`usb-wifi/manifest.json`、`usb-wifi/WHENCE` 与 `usb-wifi/licenses/` 保存配置计划、固件来源和许可证。Actions 摘要显示覆盖报告，debug 产物包含同一套元数据。
- 勾选 `make_release` 时发布独立的 `usb-wifi-*` 预发布版本，不替换已有的 Latest Release。默认仍只生成构建产物。
- 刷入前禁用或卸载原 `oneplus_wifi_lkm` 模块，刷入后重启。内建驱动不能用 `rmmod` 卸载，恢复普通版本需要刷回对应的普通内核。

45 项候选同时覆盖常见驱动和旧款网卡。只允许模块加载的驱动会跳过；部分驱动有上游实验限制，报告会保留说明。固件覆盖状态针对本次源码和清单识别出的需求，实际 USB 网卡绑定及工作情况仍需测试。

当前 OP13 6.6.118 构建保留 32 项内建 USB 网卡驱动和 67 个固件文件，配置、Image 固件内容和原厂无线 ABI 均经过构建检查。板载 WiFi 已经真机验证；具体 USB 网卡的供电、绑定和网络使用仍需实测。

本地回归检查：

```sh
python3 -m pip install --target /tmp/usb-wifi-python -r scripts/requirements-usb-wifi.txt
PYTHONPATH=/tmp/usb-wifi-python python3 -m unittest discover -s tests -v
```

## NoMount 内建支持

OP13 OOS16 的 ReSukiSU / KernelSU 两种构建默认内建 [官方 NoMount](https://github.com/maxsteeel/nomount/tree/c5fad9d8f97c5a207f7342fd91789449915ea047)。源码固定到 `profiles/nomount.json` 的提交，并验证归档 SHA256；按官方手动集成方式接入 `fs/Kconfig` / `fs/Makefile`，启用 `CONFIG_NOMOUNT=y` 和其通信所需的 `CONFIG_KEYS=y`。xattr 回调与 VFS 调用的参数根据该机型实际头文件适配，避免仅按版本号判断厂商回移接口；清单分别记录上游和适配后源码的校验值。

构建在 `olddefconfig` 后检查配置，编译后检查 `System.map` 中的初始化函数与 key type，以及本次 Image 中的初始化信息；缺失则停止打包。ZIP 和 debug 产物的 `nomount-support/` 包含提交、源码校验值、许可证和验证报告。

刷入后仍需在管理器中安装[官方 NoMount 元模块](https://github.com/maxsteeel/nomount/releases)，用于加载模块规则和提供 WebUI；内建支持无需加载 `nomount.ko`。可用元模块附带的 `nm version` 检查内核通信。OP13 6.6.118 构建已通过 NoMount 配置与 Image 链接检查。

同步上游更新时保留 OP13 OOS16 的固定构建范围、固件内建、原厂无线 ABI 检查、NoMount 和 USBWiFi 产物命名。以下保留项目来源、功能和致谢。

---

<div align="center">

# OnePlus 13 OOS16 — 基于 Huangdihd / WildKernels

[![KernelSU](https://img.shields.io/badge/KernelSU-Supported-green)](https://kernelsu.org/)
[![ReSukiSU](https://img.shields.io/badge/ReSukiSU-Supported-green)](https://resukisu.github.io/)
[![SUSFS](https://img.shields.io/badge/SUSFS-Integrated-orange)](https://gitlab.com/simonpunk/susfs4ksu)

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

## 维护目标

| 机型 | 系统 | Manifest | 配置 |
|------|------|----------|------|
| OnePlus 13 | OOS16 / 对应 ColorOS16 原厂系统 | `oneplus_13_w.xml` | `configs/oos16/OP13.json` |

## 🔗 Additional Resources

- 🩹 [Kernel Patches](https://github.com/WildKernels/kernel_patches)
- ⚡ [Kernel Flasher](https://github.com/fatalcoder524/KernelFlasher)

---

## 兼容性

详见 [compatibility.md](compatibility.md)。当前真机参考为 PJZ110、`PJZ110_16.0.10.501(CN01)`、6.6.118；不提供其他机型或旧版系统构建。

---

## ✨ Features

以下功能面向 **OnePlus 13 / OOS16 / `oneplus_13_w.xml`**。

- 🔐 **ReSukiSU / KernelSU**：默认使用官方 ReSukiSU，也可在 Actions 选择 KernelSU。
- 🥷 **SUSFS**：集成内核侧支持；配套管理功能需安装对应的 SUSFS 用户空间模块。
- 📶 **内建 USB WiFi**：当前 6.6.118 构建内建 32 项 USB 网卡驱动及 `cfg80211` / `mac80211` 等依赖，无需额外加载网卡驱动 `.ko`。
- 📦 **内建无线固件**：当前构建嵌入 67 个固件文件；ZIP 附带驱动覆盖、固件缺失、来源、校验值及许可证报告。具体网卡仍需实测。
- ✅ **板载 WiFi 兼容修复**：核对 50 个原厂无线符号 CRC，并处理内建 `cfg80211` / `rfkill` 被重复加载的问题；OP13 OOS16 6.6.118 已由用户确认开机 WiFi 正常。
- 🗂️ **内建 NoMount**：集成固定提交的官方 NoMount，启用 `CONFIG_NOMOUNT` 和 `CONFIG_KEYS`；模块规则及 WebUI 仍需官方 NoMount 元模块。
- 🔌 **USB DWC3 / OTG**：启用高通 DWC3 与 USB 双角色支持，为 USB 外设提供内核侧支持。
- 🛡️ **Baseband Guard（BBG）**：集成基于 LSM 的关键分区访问保护。
- 🛠️ **HMBIRD 调度支持**：集成 OP13 / SM8750 对应的风驰调度补丁。
- 🌐 **TCP BBR**：启用 BBR 拥塞控制及 FQ / FQ-CoDel 队列支持。
- 🚀 **ThinLTO 与优化补丁**：使用 ThinLTO，集成内存、I/O、网络等优化；Actions 可选择 O2 或 O3 编译等级。
- 🧱 **Netfilter 扩展**：集成 TTL / IPv6 Hop Limit、IP Set 与 IPv6 NAT 配置支持。
- ⚡ **TMPFS XATTR / POSIX ACL**：支持元模块等功能所需的扩展属性和访问控制列表。
- </> **Unicode 补丁**：保留实验性的 Unicode 路径兼容补丁。
- 🖥️ **Droidspaces**：集成运行 Linux 容器所需的内核支持，容器管理仍需配套用户空间工具。
- 🔃 **NTSync**：集成 Windows NT 同步原语支持，供兼容层使用。

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
