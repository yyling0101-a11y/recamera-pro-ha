# reCamera Pro for Home Assistant

[![HACS Action](https://github.com/yyling0101-a11y/recamera-pro-ha/actions/workflows/hacs.yml/badge.svg)](https://github.com/yyling0101-a11y/recamera-pro-ha/actions/workflows/hacs.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

本项目是面向 reCamera Pro 原厂固件的 Home Assistant 本地自定义集成，提供多设备管理、MQTT 推理事件、WebRTC 实时预览、AcousticsLab 声音规则和 HA Bus 事件。

This is a local Home Assistant custom integration for factory reCamera Pro firmware. It provides multi-device management, MQTT inference events, WebRTC preview, AcousticsLab sound rules, and HA Bus events.

## 重要边界 / Compatibility boundary

- 集成不会修改、上传或在 reCamera 上运行额外代码。
- MQTT 只订阅用户配置的原厂事件 Topic，不要求额外的 presence/LWT Topic。
- 当前只支持原厂 `detection`、`classification`、`segmentation` 三种推理结果。
- “Broker 已连接”表示 HA 客户端已成功连接 Broker；“正在接收”表示最近 90 秒收到过原厂推理消息。后者不是独立的设备在线探测。

The integration never modifies or uploads code to the camera. It subscribes only to the configured factory event topic and supports factory detection, classification, and segmentation payloads.

## 前置条件 / Requirements

- Home Assistant **2025.1** 或更新版本，管理员账号（侧边栏面板 `require_admin`）。
- 运行**原厂固件**的 reCamera Pro，与 Home Assistant 处于同一局域网。
- 一个 **MQTT Broker**：HA OS 可安装 “Mosquitto broker” 加载项；HA Container 可用 `install.sh --mqtt=create` 创建独立 Sidecar。
- Python 依赖 `aiomqtt==2.5.1` 已声明在 `manifest.json`，由 Home Assistant 自动安装，无需手动 `pip install`。

- Home Assistant **2025.1** or newer, with an admin account (the sidebar panel is admin-only).
- A reCamera Pro running **factory firmware**, on the same LAN as Home Assistant.
- An **MQTT broker**: install the “Mosquitto broker” add-on on HA OS, or let `install.sh --mqtt=create` create an isolated sidecar on HA Container.
- The `aiomqtt==2.5.1` dependency is declared in `manifest.json` and installed automatically by Home Assistant.

## 安装 / Installation

### 方式一：HACS（HA OS / Supervised / Container 通用，推荐）

先安装 [HACS](https://hacs.xyz)，然后：

1. HACS → 右上角 **⋮** → **Custom repositories**（自定义仓库）。
2. 仓库地址填下面这一行，**Category 选择 Integration**，保存：

   ```text
   https://github.com/yyling0101-a11y/recamera-pro-ha
   ```

3. HACS → **Integrations** → 搜索 **reCamera Pro** → **Download**（首次安装 HACS 会自动重载自定义组件，通常无需重启；若“添加集成”里搜不到，重启一次 Home Assistant 即可）。
4. **设置 → 设备与服务 → 添加集成** → 搜索 **reCamera Pro** → 填写一台在线 reCamera 的 IP / 设备账号 / 密码 → 提交。
5. 添加成功后，侧边栏自动出现 **reCamera Pro** 面板，**无需任何 YAML 或终端操作**。

> 说明：侧边栏面板、静态资源和 HTTP API 在集成被加载时注册；通过“添加集成”创建设备条目即可触发加载，因此**正常流程不需要写 `configuration.yaml`**。
> 只有当你想在**尚未添加任何摄像机**时就先看到面板，才需要手动在 `configuration.yaml` 加一行 `recamera_pro:` 并重启（HAOS 上可用 Studio Code Server / Terminal 等加载项编辑）。

HACS 负责安装、升级和卸载集成代码。删除单台摄像机请在 reCamera Pro 侧边栏设备卡片或 Home Assistant 的“设备与服务”中完成。

Install [HACS](https://hacs.xyz), add `https://github.com/yyling0101-a11y/recamera-pro-ha` as a **custom repository** with category **Integration**, then download **reCamera Pro**. Next go to **Settings → Devices & Services → Add integration → reCamera Pro** and add a camera; the sidebar panel appears automatically — no YAML or terminal needed. The `recamera_pro:` line in `configuration.yaml` is only required if you want the panel visible before adding any device.

### 方式二：Home Assistant Apps 安装（HA OS / Supervisor）

适用于 **Home Assistant OS** 和其他支持 Supervisor Apps 的安装，不适用于普通 **Home Assistant Container**。本仓库同时是一个 **Home Assistant App（旧称加载项）仓库**，内含一次性安装器
`recamera-pro-installer`：它把 `custom_components/recamera_pro` 复制到
`/config/custom_components/`，全程只需在网页界面点几下。

[![打开 Home Assistant 并添加本仓库](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fyyling0101-a11y%2Frecamera-pro-ha)

1. 打开 **Settings → Apps → Install app → Repositories**（部分旧版显示为 **Settings → Add-ons → Add-on Store → ⋮ → Repositories**）。
2. 添加下面的 GitHub 仓库 URL 并保存：

   ```text
   https://github.com/yyling0101-a11y/recamera-pro-ha
   ```

3. 找到 **reCamera Pro Installer**，点击 **Install**，安装完成后点击 **Start**。安装器运行一次后自动停止，日志出现 `reCamera Pro <版本> is installed` 即成功。设备需要能访问 GitHub 和 `ghcr.io` 下载预构建 App 镜像；若还不能下载，请确认维护者已将 GHCR package 设为 Public。
4. 安装后需要重启 Home Assistant Core：**Settings → System → 右上角 ⋮ → Restart Home Assistant**。安装器不会调用 Supervisor API 或自动重启 Core。
5. **设置 → 设备与服务 → 添加集成 → reCamera Pro**，填写一台在线 reCamera 的
   IP / 设备账号 / 密码。侧边栏面板随后自动出现，**不需要写任何 YAML**。

Apps 安装的是 **reCamera Pro 集成安装器**；实际摄像机管理、MQTT、WebRTC、设备配置和侧边栏面板仍由 Custom Integration 提供。安装器不修改 `configuration.yaml`，也不需要 SSH、终端或 HACS。MQTT Broker 仍需提供：HA OS 可在内置商店安装 **Mosquitto broker**。

> 升级：维护者更新 `recamera-pro-installer/Dockerfile` 中固定的源码 commit 和 SHA-256，并同步更新集成/App 版本；用户在商店中点 **更新** 后重新启动安装器。旧版本会被移动到
> `/config/.recamera-pro-backups/`，不会直接删除。
> 镜像由 GitHub Actions 预构建并发布到 GHCR；仓库维护者首次发布后需在 GitHub 的 **Packages → Package settings** 将 Container package 设为 **Public**。
> 已由 HACS 管理 `recamera_pro` 的用户应继续通过 HACS 更新；若检测到 HACS 和已有同名集成，Apps 安装器会停止，避免两个更新机制管理同一目录。
> 卸载集成：卸载该加载项不会删除集成文件，请删除
> `/config/custom_components/recamera_pro` 后重启（详见
> [`recamera-pro-installer/DOCS.md`](recamera-pro-installer/DOCS.md)）。

For English instructions, follow **Settings → Apps → Install app → Repositories**,
add the repository URL above, install and start **reCamera Pro Installer**, restart
Home Assistant Core, then add **reCamera Pro** under **Settings → Devices & Services**.
The App is only an installer; all camera features are provided by the Custom
Integration. This method requires Home Assistant OS or another Supervisor Apps
installation and does not apply to plain Home Assistant Container. See
[`recamera-pro-installer/DOCS.md`](recamera-pro-installer/DOCS.md).

### 方式三：手动安装（任何部署方式）

```sh
cd /path/to/home-assistant-config/custom_components
git clone --depth 1 https://github.com/yyling0101-a11y/recamera-pro-ha.git /tmp/recamera-pro-ha
cp -r /tmp/recamera-pro-ha/custom_components/recamera_pro ./recamera_pro
rm -rf /tmp/recamera-pro-ha
```

随后在 `configuration.yaml` 加入 `recamera_pro:` 并重启 Home Assistant。HA OS 用户可通过 **Advanced SSH & Web Terminal**、**Terminal & SSH** 或 **Studio Code Server** 加载项执行上述命令（配置目录挂载在 `/config`）。

### 方式四：一键脚本（HA Core / 官方 HA Container）

解压发布包后运行：

```sh
sudo ./install.sh install
./install.sh status
sudo ./install.sh uninstall
```

脚本会优先使用 `/config`，也能从单个正在运行的官方 Home Assistant Docker 容器识别 `/config` 挂载。无法唯一识别时请明确传入配置目录：

```sh
sudo ./install.sh install /path/to/home-assistant-config
```

安装采用临时目录与原子移动，并备份旧版本。卸载只接受带有本安装器标记且 manifest 域为 `recamera_pro` 的目录，然后将其移动到 `.recamera-pro-backups`，不会递归删除其他集成或用户配置。脚本只移除自己写入的 YAML 标记块。

HA OS、Supervised 以及无法从宿主机写入 `/config` 的部署请使用方式一（HACS）或方式二（加载项仓库）。无法安全承诺一个宿主机脚本覆盖所有第三方 Docker 封装、权限模型和只读挂载；HACS 是 Home Assistant 生态中面向这些环境的标准安装/升级/卸载方式。

## MQTT Broker 自动处理 / Broker auto-setup

Home Assistant Container 包含 MQTT 集成，但不自带 Broker。安装操作未传 `--mqtt` 时默认使用保守的 `--mqtt=auto`：

```sh
# 默认：检测已有环境；确认没有 Broker 才创建 Sidecar
sudo ./install.sh install --mqtt=auto

# 明确使用已有 Broker
sudo ./install.sh install --mqtt=existing

# 明确创建项目托管 Broker
sudo ./install.sh install --mqtt=create --broker-host=192.168.1.10

# 完全不处理 MQTT
sudo ./install.sh install --mqtt=skip
```

自动检测会依次识别项目托管容器、插件已有 Broker 设置、HA MQTT Config Entry、常见 Broker 容器以及宿主机 1883 监听端口。检测到任意已有环境时不会创建、停止或修改 Broker；无法检查 Docker 时也不会擅自安装。

确认没有 Broker 后，脚本使用固定版本 `eclipse-mosquitto:2.0.22` 创建独立的 `recamera-pro-mqtt` Sidecar，默认关闭匿名访问，配置和数据只存放在 `/config/recamera_pro_broker/`。生成的 HA 账户会被插件自动读取；设备账户供用户填写到 reCamera 原厂 WebUI：

```sh
sudo ./install.sh credentials
```

卸载集成默认保留 Broker：

```sh
sudo ./install.sh uninstall                 # 保留 Broker
sudo ./install.sh uninstall --mqtt=remove   # 只移除带项目标签的 Broker
```

Broker 卸载会验证容器标签、目录路径和管理标记，将数据移动到 `.recamera-pro-backups`，不会删除 Docker 镜像，也不会处理用户自有 Broker。

Home Assistant Container includes the MQTT integration but no broker. Install defaults to conservative `--mqtt=auto`: an isolated Mosquitto sidecar is created only when no existing MQTT configuration, listener, or broker container is detected. Integration removal keeps the broker unless `--mqtt=remove` is explicitly supplied.

## Python 依赖 / Python dependencies

`aiomqtt==2.5.1` 已声明在集成的 `manifest.json` 中，由 Home Assistant 的集成依赖管理器安装。安装脚本不会向系统 Python 或 HA 容器执行任意 `pip install`，避免污染用户环境。

## MQTT

- Broker 地址是 HA 与 reCamera 原厂通知服务共同连接的 MQTT 服务器地址。
- 用户名和密码必须是 Broker 中已经创建的账户；插件保存前会验证鉴权。
- 事件 Topic 承载原厂推理 JSON。
- 视觉事件规则可按任务类型、类别和置信度触发 HA Bus 事件；缺少前缀时会自动添加 `recamera_`。

Broker credentials must already exist on the Broker. The integration validates them before saving. Visual rules match task type, class, and confidence and fire HA Bus events with a `recamera_` prefix.

## 许可证 / License

Apache License 2.0，详见 [LICENSE](LICENSE)。

Apache License 2.0. See [LICENSE](LICENSE).
