# 一加 13 ColorOS 17

`main` 只维护 `PJZ110_17.0.0.103(CN01)` / Linux 6.6.118。默认构建、工具链镜像、自动上游同步和 Release 均使用 `configs/cos17/OP13.json` 与 `manifests/cos17/oneplus_13_w.xml`。

在 GitHub Actions 运行 **OnePlus 13 ColorOS 17 Quick Build** 可生成 BakaSU 刷机包。勾选 `make_release` 会使用干净构建并发布公开的 GitHub 预发布版。通过 **Build OnePlus 13 ColorOS 17 (Built-in USB WiFi)** 可选择 KernelSU、指定 BakaSU/SUSFS 提交或调整编译选项。

## 源码与无线 ABI

截至 2026-11-22，OnePlusOSS 的 OP13 SM8750 common、vendor kernel、modules/device-tree 和 manifest 仍未公开单独的 C17 基线。本项目沿用其 `oneplus/sm8750_b_16.0.0_oneplus_13` 源码。HMBIRD 与 NTSync 采用这份源码对应的 A16 补丁。

`profiles/vendor-wifi-abi/op13-cos17-6.6.118.json` 来自该 C17 版本的 `vendor_boot_b.img`。原厂 `cfg80211.ko` 的 SHA-256 为 `6896d8c806e5eeb9281f7156f591ad00b8ac16cfd11121387da03aeac8a97132`。打包检查 43 个 cfg80211 导出和 7 个 rfkill 导入的 CRC。高通 WLAN 模块完整导入尚待独立审计，报告保留 `factory_wlan_imports: unverified`。

## 刷机包与验证

刷入前备份当前启动镜像，停用原 `oneplus_wifi_lkm` 模块。使用兼容的 AnyKernel3 刷入工具安装 `AK3_OP13_COS17_*_USBWiFi.zip`。ZIP 中的 `usb-wifi.config.txt`、`usb-wifi/vendor-abi.txt` 与 `hybridmount-support/report.txt` 是本次构建的驱动、ABI 和链接记录，可与 Release 内的 SHA-256 一并核验。

此前 C17 基线（BakaSU 35257 / SUSFS v2.3.0）在 GitHub Actions 完成全量编译，确认 32 个内建 USB WiFi 驱动、67 份固件、50 项无线符号 CRC 及 Hybrid Mount 链接。C17 真机启动、板载 WiFi、USB 硬件和实际挂载规则仍待验证。[2026-11-04 基线验证](https://github.com/chorusfruit-233/OnePlus_BakaSU_SUSFS_EXTEND/actions/runs/41737681933)
