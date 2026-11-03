# OnePlus 13 OOS16 / ColorOS17 兼容性

本项目只维护 OP13，配置与 manifest 分别位于 `configs/{oos16,cos17}/` 和 `manifests/{oos16,cos17}/`。OOS16 为默认目标，COS17 为实验目标。

| 项目 | 维护范围 |
|------|----------|
| 机型 | OnePlus 13（OP13 / sun / SM8750） |
| 系统 | OOS16 / 对应 ColorOS16；实验性 ColorOS17 17.0.0.103 |
| 源码分支 | `oneplus/sm8750_b_16.0.0_oneplus_13` |
| 内核系列 | android15-6.6 |
| OOS16 真机参考 | PJZ110 / `PJZ110_16.0.10.501(CN01)` / 6.6.118 |
| COS17 实验参考 | PJZ110 / `PJZ110_17.0.0.103(CN01)` / 6.6.118 |

OOS16 板载 WiFi 已由用户在真机确认修复后正常，包括重启后的首次开启。构建核对原厂无线模块的 50 个符号 CRC，并处理内建 `cfg80211` / `rfkill` 的重复加载。USB 网卡驱动与可获取的固件内建，具体网卡仍需实测。

COS17 使用独立的 50 项 `cfg80211` / `rfkill` CRC 参考，不能替代高通 WLAN 模块完整导入审计及真机验证。目前沿用已公开的 OOS16 / 6.6.118 源码，HMBIRD 和 NTSync 按该源码选择 A16 补丁。无匹配 ABI 参考或 CRC 不匹配时停止构建、禁止打包；完整说明见 [ColorOS17 适配](docs/cos17.md)。

其他机型、OOS14/OOS15、`oneplus_13_6.6.89_w.xml`、非原厂 ROM 不在维护范围。系统更新后，应重新核对原厂模块 ABI；不能仅凭相同内核系列推断兼容。

项目来源与交流：[huangdihd](https://t.me/huangdihd)、[huangdihd_wildkernel](https://t.me/huangdihd_wildkernel)。
