# reCamera Pro for Home Assistant

本项目是面向 reCamera Pro 原厂固件的 Home Assistant 本地自定义集成，提供多设备管理、MQTT 推理事件、WebRTC 实时预览、AcousticsLab 声音规则和 HA Bus 事件。

This is a local Home Assistant custom integration for factory reCamera Pro firmware. It provides multi-device management, MQTT inference events, WebRTC preview, AcousticsLab sound rules, and HA Bus events.

## 重要边界 / Compatibility boundary

- 集成不会修改、上传或在 reCamera 上运行额外代码。
- MQTT 只订阅用户配置的原厂事件 Topic，不要求额外的 presence/LWT Topic。
- 当前只支持原厂 `detection`、`classification`、`segmentation` 三种推理结果。
- “Broker 已连接”表示 HA 客户端已成功连接 Broker；“正在接收”表示最近 90 秒收到过原厂推理消息。后者不是独立的设备在线探测。

The integration never modifies or uploads code to the camera. It subscribes only to the configured factory event topic and supports factory detection, classification, and segmentation payloads.

## 安装 / Installation

### HACS（开源发布推荐）

1. 将仓库添加为 HACS 自定义仓库，类别选择 **Integration**。
2. 安装 **reCamera Pro**。
3. 在 `configuration.yaml` 添加：

```yaml
recamera_pro:
```

4. 重启 Home Assistant，随后从侧边栏添加设备。

HACS 负责安装、升级和卸载集成代码。删除单台摄像机请在 reCamera Pro 侧边栏设备卡片或 Home Assistant 的“设备与服务”中完成。

### 一键脚本（HA Core / 官方 HA Container）

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

HA OS、Supervised 以及无法从宿主机写入 `/config` 的部署请使用 HACS。无法安全承诺一个宿主机脚本覆盖所有第三方 Docker 封装、权限模型和只读挂载；HACS 是 Home Assistant 生态中面向这些环境的标准安装/升级/卸载方式。

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
