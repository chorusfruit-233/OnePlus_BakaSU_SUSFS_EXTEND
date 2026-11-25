# 一加 13 ColorOS 17 兼容性

| 项目 | 唯一维护目标 |
| --- | --- |
| 机型 | OnePlus 13，PJZ110，SM8750 / sun |
| 原厂系统 | `PJZ110_17.0.1.202(CN01)` |
| 内核 | android15-6.6.118 |
| 公开源码基线 | `oneplus/sm8750_b_16.0.0_oneplus_13` |
| 配置 | `configs/cos17/OP13.json` |
| Manifest | `manifests/cos17/oneplus_13_w.xml` |

打包前按原厂模块核对 50 项无线 CRC 和 16 项蓝牙、TLS、内存回收 CRC。参考缺失或任何一项不符时停止打包。三款高通 WLAN 驱动的符号导入已通过静态检查。C17 启动、板载 Wi-Fi 和具体 USB 网卡仍需实测。系统升级后需要对应版本的原厂 ABI 参考。[参考来源与构建说明](docs/cos17.md)
