# OP13 ColorOS 17 构建依赖

2026-11-24 核对了以下构建依赖。当前目标为 `PJZ110_17.0.1.202(CN01)` / android15-6.6.118。两条上游的合并历史均保留在 `main`。

| 上游 / 依赖 | 核对的提交或版本 |
| --- | --- |
| huangdihd/OnePlus_BakaSU_SUSFS | `4cdf2311bc02555da0898a7de187cd63e239ff12` |
| WildKernels/OnePlus_KernelSU_SUSFS | `34eae44087999a2d5d1371b3fb1551fad711d32b`，较上次新增 2 个提交 |
| Baka-SU/BakaSU main | `57b2db6076f439cfd489f14576444e8f0f2f0a25` |
| tiann/KernelSU main | `2a60b2893b8d0d885d1ceff2287d8ad854f0e0f4` |
| simonpunk/susfs4ksu gki-android15-6.6 | `f98f08223bbf469cc0a1542166383d253557fc32`，v2.4.0 |
| WildKernels/kernel_patches main | `70c394f16d82b0f85a4f07617630d82dde6d203c` |
| vc-teahouse/Baseband-guard main | `48d9fdea643bcb41d204541400e9d8656b97a54f` |
| huangdihd/AnyKernel3 gki-2.0 | `ea531d03965f702a45e1b0ab7c5db8d196c975c3` |
| Hybrid Mount VFS | v6.2.6 / `0a047415b795e760bfdb84e98ef7d4b653485c50`，归档 SHA-256 `ab2f2d47c62516eb7c46627e782e563c5a7430dab338ef751cfc07d49a0154b3` |
| OnePlusOSS OP13 common / modules & DT | `e1b346b6b4f4096eb342ae3684838a942fd6f6c4` / `d50b305f7da9e14715a25120a4ac7b1a4b8b97c3` |
| OnePlusOSS kernel_manifest oneplus/sm8750 | `f8e50677874c65b6da41057d2f39be7b4ef3c08a` |
| 官方 manifest 的 build-tools / Android Clang | `434f141b6d22a773a163fa9c707b19b4d254d989` / `b099698c583b8361ca771f3cc8d6af6f729f39b3` |
| 实际编译器 | ZyC Clang `19.0.0git-20240723-release`，当前 19 系列的最终标签 |
| linux-firmware | 发布 `20261019` / `a2dcb924f0897368b0b4f305cbf9808cdda90ce0`，Git 根树与 WHENCE 哈希已复核 |
| wireless-regdb / ZD1211 | `2026.09.03` / `1.5`，保留 `2023.09.01` 监管数据库以匹配旧签名证书 |
| kconfiglib | PyPI `14.1.0` |
| GitHub Actions | checkout `v7.0.1`、cache `v6.1.0`、setup-python `v7.1.0`、github-script `v9.0.0`、upload-artifact `v7.0.2`、download-artifact `v8.0.2` |
| OpenCode GitHub Action | `v1.19.6` |

WildKernels 本轮修复模块覆盖复制与 ccache 哈希输入。C17 已按优先级复制模块，本次将选中的模块路径传给 `CCACHE_EXTRAFILES`。BakaSU 包含 SELinux 上下文映射修复，Baseband Guard 更新了新版 Linux 的 LSM 接口适配。BakaSU 与 Baseband Guard 继续跟踪各自的 `main`，SUSFS 保持 v2.4.0。

分支跟踪依赖以每次构建实际解析结果为准。Hybrid Mount 与固件归档在构建时校验，Release 附实编刷机包的 SHA-256 与来源提交。旧版本构建范围及验证记录可查阅[上次发布的依赖审计](https://github.com/chorusfruit-233/OnePlus_BakaSU_SUSFS_EXTEND/blob/22a132ee6b7f9509fc78c66b1eb63c8565c892c9/docs/dependency-status.md)。
