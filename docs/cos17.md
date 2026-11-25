# 一加 13 ColorOS 17

`main` 只维护 `PJZ110_17.0.1.202(CN01)` / Linux 6.6.118。默认构建、工具链镜像、自动上游同步和 Release 均使用 `configs/cos17/OP13.json` 与 `manifests/cos17/oneplus_13_w.xml`。

在 GitHub Actions 运行 **OnePlus 13 ColorOS 17 Quick Build** 可生成 BakaSU 刷机包。勾选 `make_release` 会使用干净构建并发布公开的 GitHub 预发布版。通过 **Build OnePlus 13 ColorOS 17 (Built-in USB WiFi)** 可选择 KernelSU、指定 BakaSU/SUSFS 提交或调整编译选项。

## 源码与原厂模块 ABI

构建沿用 OnePlusOSS 的 `oneplus/sm8750_b_16.0.0_oneplus_13` 公开源码。HMBIRD 与 NTSync 采用这份源码对应的 A16 补丁。原厂内核为 `6.6.118-android15-8-gb1422e39c313-abogki552867473-4k`。

从 `PJZ110_17.0.1.202(CN01)` 全量 OTA（`PJZ110_11.F.10_2100_202611130306`）提取 `vendor_boot`、`vendor_dlkm` 和 `system_dlkm`。以 OTA manifest 的 SHA-256 核对分区，并确认其 `boot` 与已提供的原厂镜像完全一致。分区、`cfg80211.ko` 和 `rfkill.ko` 的哈希记录在 `profiles/vendor-wifi-abi/op13-cos17-6.6.118.json`。[全量 OTA 索引](https://fwatlas.com/oneplus/oneplus-13/pjz110-17-0-1-202-cn01-pjz110-11-f-10-2100-202611130306)

- 核对了 712 份去重后的原厂模块的版本化导入。三款高通 WLAN 驱动（kiwi v2、peach、peach v2）各有 43 项内建无线依赖，全部匹配。
- 按原厂关闭 `CONFIG_BPF_STREAM_PARSER`，恢复 `bluetooth.ko` 和 `tls.ko` 使用的 15 项 CRC。
- 回移 Android 公共内核的 `android_vh_mm_get_zone_mark`，在 `pgdat_balanced()` 的水位检查前调用，供 `oplus_bsp_zram_opt.ko` 使用。[Android 公共内核源码](https://android.googlesource.com/kernel/common/+/329f9ae918a9e18da3c488e531adf9b7995e2aae/mm/vmscan.c)
- 编译后核对上述 16 项和 50 项无线 CRC。所有符号都必须是内建内核导出，校验通过后才能打包。

## 刷机包与验证

刷入前备份当前启动镜像，停用原 `oneplus_wifi_lkm` 模块。使用兼容的 AnyKernel3 刷入工具安装 `AK3_OP13_COS17_*_USBWiFi.zip`。ZIP 中的 `usb-wifi.config.txt`、`usb-wifi/vendor-abi.txt` 与 `hybridmount-support/report.txt` 是本次构建的驱动、ABI 和链接记录，可与 Release 内的 SHA-256 一并核验。

此前 C17 基线（BakaSU 35257 / SUSFS v2.3.0）在 GitHub Actions 完成全量编译，确认 32 个内建 USB WiFi 驱动、67 份固件、50 项无线符号 CRC 及 Hybrid Mount 链接。C17 真机启动、板载 WiFi、USB 硬件和实际挂载规则仍待验证。[2026-11-04 基线验证](https://github.com/chorusfruit-233/OnePlus_BakaSU_SUSFS_EXTEND/actions/runs/41737681933)
