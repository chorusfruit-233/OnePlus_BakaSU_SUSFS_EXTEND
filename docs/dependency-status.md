截至 2026-11-03，已核对 WildKernels 主上游及全部构建依赖。本轮同步目标为 `11821d9e122629d0888382f588954ef79ee88af6`，相对上次已合并的 `ce52f331beea06a0c693ec58cb1b62a08446f5ac` 新增 12 个提交；同步提交保留上游合并历史。

同时核对直接父仓库 Huangdihd 的 `797e00bdc50698e6ebfbeac736a5fe713cf819d2`。在单 OP13 范围内合入 namespace 补丁上下文恢复、精确保留产物型号和发布前产物校验；仅针对其他 SoC 的 BBG efisp 选择菜单不引入 OP13。继续保留新版 BakaSU 的 `ksu_install_su_fd()` 原生集成，不恢复父仓库中针对旧实现的删除逻辑。

上述上游同步的构建验证范围为 OP13 / OOS16 / GKI android15 / Linux 6.6.118。应用上游的 Ubuntu 24.04 runner 固定、Droidspaces 的 `CONFIG_MACVLAN=y` 和 HMBIRD 分支修正；新机型的配置与 manifest、其他 Android/内核版本专用的补丁上下文调整不在维护范围内，未恢复已经删除的目标或 kernel-monitor 工作流。USB WiFi 驱动、固件内建、Hybrid Mount VFS 与原厂无线 ABI 检查继续保留。

随后将旧 C17 实验分支适配到这一主线：增加 OP13 / COS17 17.0.0.103 独立入口，沿用当前依赖、源码和工具链，保留各自的无线 ABI 参考；OOS16 仍为默认目标。自动同步保护和工具链镜像同时覆盖两个显式目标。C17 的实验范围及本轮验证记录见 [ColorOS17 适配](cos17.md)。 C17 本轮通过 110 项回归、BakaSU 35257 / SUSFS v2.3.0 完整构建及实际产物检查；50 项 CRC 的结论限定为独立的 C17 cfg80211/rfkill 参考，尚无 C17 真机启动结论。

固定依赖的核对结果：

| 依赖 | 当前版本或提交 | 本轮处理 |
| --- | --- | --- |
| Hybrid Mount VFS | `89f328fd945c72794a6505d779f6d85834d131a3` | 上游未变化；重新验证归档 SHA256，保留 `hybridmount` / `hm1` 协议 |
| linux-firmware | `20261019` / `a2dcb924f0897368b0b4f305cbf9808cdda90ce0` | 仍为最新稳定发布；重新核对 Git 根树与 WHENCE SHA256 |
| wireless-regdb | `2026.09.03` | 仍为最新发布，归档 SHA256 核对通过；保留 `2023.09.01` 以匹配旧内核信任证书 |
| ZD1211 firmware | `1.5` | 保留现有官方固件包与 SHA256 |
| kconfiglib | `14.1.0` | 仍为 PyPI 最新版本 |
| actions/checkout | `v7.0.1` | 仍为当前发布版 |
| actions/cache | `v6.1.0` | 仍为当前发布版 |
| actions/setup-python | `v7.1.0` | 仍为当前发布版；测试解释器使用 Python 3.12 |
| actions/github-script | `v9.0.0` | 仍为当前发布版 |
| actions/upload-artifact | `v7.0.2` | 共享中间产物和最终产物使用同一上传版本 |
| actions/download-artifact | `v8.0.2` | 与上传端配套 |
| anomalyco/opencode/github | `v1.19.5` | 从 v1.19.4 更新；Action 输入及实现兼容，其内部 CLI 继续由上游 Action 安装 |

以下源码在每次构建时按所选分支解析或下载，本轮核对的提交如下。审计快照不替代用户选择的分支或提交。

| 依赖 | 跟踪分支 | 本轮核对的提交 |
| --- | --- | --- |
| Baka-SU/BakaSU | `main` | `516d3e87fbc986ccefdde2c2765f1700612441a9` |
| tiann/KernelSU | `main` | `28db74f6f4692e97006ce9ebd8b19b9cc614b5b7` |
| simonpunk/susfs4ksu | `gki-android15-6.6` | `c7f670f57b7d43d75066b6657f8aee9cdf580d96`（v2.3.0） |
| WildKernels/kernel_patches | `main` | `ee68218dc83b3e488ae619eb82e868859e8eb17d` |
| vc-teahouse/Baseband-guard | `main` | `028ff7fd509e2104596da7cc1ef8e6ce2a0c9082` |
| huangdihd/AnyKernel3 | `gki-2.0` | `ea531d03965f702a45e1b0ab7c5db8d196c975c3`（未变化） |
| OnePlusOSS common kernel | `oneplus/sm8750_b_16.0.0_oneplus_13` | `e1b346b6b4f4096eb342ae3684838a942fd6f6c4`（未变化） |
| OnePlusOSS modules/device tree | `oneplus/sm8750_b_16.0.0_oneplus_13` | `d50b305f7da9e14715a25120a4ac7b1a4b8b97c3`（未变化） |

BakaSU 本轮新增 SELinux inode/BTF 兼容处理；内建模式继续使用目标内核的类型布局。Droidspaces、NTSync、调度及优化补丁通过 `kernel_patches` 跟进；自定义 ccache 二进制也跟随该仓库，每轮矩阵只下载一次，下载失败时保留 apt 回退。BBG 继续由官方 setup 脚本集成。AnyKernel3 每次直接同步所选分支；SUSFS 按构建开始时解析的提交下载一次并在构建矩阵中复用，API 与旧归档 URL 的共享归档适配保留。namespace 恢复仅接受一个已知头文件/声明 hunk；额外功能改动、多个 hunk 或不符合预期的锚点都保留 `.rej`，继续走原有错误输出。

兼容约束：

- OnePlus `kernel-build-tools` 固定 `434f141b6d22a773a163fa9c707b19b4d254d989`；Android Clang 预编译工具固定 `b099698c583b8361ca771f3cc8d6af6f729f39b3`。本轮再次与官方 OP13 manifest 核对一致。官方完整 Android 构建树中的 JDK、测试工具及其他未使用预编译项目未引入当前直接 make 构建。
- 默认 ZyC Clang 保持 `19.0.0git-20240723-release`。最新发布顺序指向 Clang 14，而最高数字版本 Clang 23 为开发构建；本轮使用现有工具链验证新的依赖组合。
- 原厂无线 ABI 参考仍限定 `PJZ110_16.0.10.501(CN01)` / 6.6.118。系统或内核版本改变后，仍需相应原厂模块重新建立参考。
- Rust 构建仍关闭；不启用 Rust、bindgen 或其他机型专用依赖。

发布时按 `archive: false` 的实际文件名分别下载 `matrix.json` 和 `AK3_*_USBWiFi.zip` artifacts，使用 `skip-decompress: true` 保留原始文件，排除共享构建工具和 debug 内容；创建标签前验证矩阵数量、目标对应关系、ZIP CRC、非空 `Image` 与 `anykernel.sh`，避免发布外层 artifact ZIP 或留下缺失产物的标签。独立的 `usb-wifi-*` 预发布命名仍保留。

BakaSU 35252 及当前后续版本已由 ksud 从 `/data/adb/ksu/.susfs.json` 恢复 SUSFS 配置。旧版自动生成的 `susfs_manager` v1.0.2 模块可能仍携带旧 uname 和日志开关，在 ksud 之后覆盖运行值；它的“请勿删除”说明属于旧版模板。遇到配置文件不变、重启后 uname 回退时，先停用旧模块并验证；其中需要保留的自定义规则应备份或迁移到当前管理方式。

`.github/dependabot.yml` 继续每周跟进 GitHub Actions 与 `scripts/requirements-usb-wifi.txt`。WildKernels 同步可在 `opencode` 工作流中留空 prompt 手动触发，原有注释的 schedule 不变。同步流程保留两亲合并历史，并在旧 sanitizer 后执行 `scripts/maintain_target.py`；快速 PR 路径也校验单 OP13 目标和 BakaSU 命名。`.github/opencode/` 内文件保持原样。

本轮验证使用 GitHub Actions 的 Ubuntu 24.04 runner。云执行环境不可用，因此未将上次的本地主机或 Docker 检查冒充本轮验证。元数据与校验和审计见[审计运行](https://github.com/chorusfruit-233/OnePlus_BakaSU_SUSFS_EXTEND/actions/runs/41698415381)。

本轮验证结果：

- [回归与发布流程验证](https://github.com/chorusfruit-233/OnePlus_BakaSU_SUSFS_EXTEND/actions/runs/41706275378)：102 项测试通过，工作流 YAML、嵌入的 Bash/Python 和单 OP13 目标检查通过；实际下载原始矩阵及 BakaSU 刷机 ZIP 后，产物数量、目标、内容和 CRC 校验通过，并验证校验步骤位于创建标签之前。
- [BakaSU 35257 完整构建](https://github.com/chorusfruit-233/OnePlus_BakaSU_SUSFS_EXTEND/actions/runs/41698956616)与 [KernelSU 32716 完整构建](https://github.com/chorusfruit-233/OnePlus_BakaSU_SUSFS_EXTEND/actions/runs/41698956775)均使用清理缓存后的构建，内核为 6.6.118，SUSFS 为 v2.3.0。两套产物均验证 32 个内建 USB WiFi 驱动、67 个固件、50 项匹配原厂的无线符号 CRC，以及 Hybrid Mount 的 Image/System.map 链接。

完整编译使用验证分支的 `b28a6be`，覆盖更新后的源码依赖、runner 和 MACVLAN 变更；随后加入的 namespace 兜底与发布流程调整由上述回归和实际产物验证覆盖。未进行真机启动验证。
