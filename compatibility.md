# OnePlus 13 OOS16 兼容性

本项目仅维护 `configs/oos16/OP13.json` 和 `manifests/oos16/oneplus_13_w.xml`。

| 项目 | 维护范围 |
|------|----------|
| 机型 | OnePlus 13（OP13 / sun / SM8750） |
| 系统 | OOS16 / 对应 ColorOS16 原厂系统 |
| 源码分支 | `oneplus/sm8750_b_16.0.0_oneplus_13` |
| 内核系列 | android15-6.6 |
| 已验证原厂版本 | PJZ110 / `PJZ110_16.0.10.501(CN01)` / 6.6.118 |

板载 WiFi 已由用户在真机确认修复后正常，包括重启后的首次开启。构建核对原厂无线模块的 50 个符号 CRC，并处理内建 `cfg80211` / `rfkill` 的重复加载。USB 网卡驱动与可获取的固件内建，具体网卡仍需实测。

其他机型、OOS14/OOS15、`oneplus_13_6.6.89_w.xml`、非原厂 ROM 不在维护范围。系统更新后，应重新核对原厂模块 ABI；不能仅凭相同内核系列推断兼容。

项目来源与交流：[huangdihd](https://t.me/huangdihd)、[huangdihd_wildkernel](https://t.me/huangdihd_wildkernel)。
