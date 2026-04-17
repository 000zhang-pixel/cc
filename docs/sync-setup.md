# Windows ↔ Mac 双平台运行方案

**目标**: Windows 生成的内容（`content-store/`）自动同步到 Mac；代码通过 GitHub 保持两端一致。

---

## 分工：代码 vs 内容文件

| 类型 | 同步方式 | 原因 |
|------|----------|------|
| **代码**（`middleware/`、`publish-engine/`、`docs/`） | **GitHub** | 文本文件，版本管理，PR 流程 |
| **内容文件**（`content-store/`，图片/视频/json/txt） | **Syncthing** | 二进制文件不适合 Git；需要实时同步 |

`content-store/` 已在 `.gitignore` 中排除，不会上传到 GitHub。

---

## 代码同步：GitHub

### 日常操作

```bash
# Windows（生产变更后）
git add .
git commit -m "feat: ..."
git push

# Mac（同步最新代码）
git pull
```

### Mac 首次克隆

```bash
mkdir -p ~/workspace
cd ~/workspace
git clone https://github.com/000zhang-pixel/cc.git ai-content-hub
cd ai-content-hub/middleware
pip install -r requirements.txt
cp .env.mac.example .env
# 编辑 .env，填入真实 API Keys
```

> 说明：仓库代码统一放在 `~/workspace/ai-content-hub`；`middleware/.env` 是本机配置，不通过 Git 跨机器覆盖。

---

## 内容文件同步：Syncthing

### 选型理由

| 方案 | 优点 | 缺点 |
|------|------|------|
| **Syncthing** ✅ | 免费开源；P2P 直连，局域网极快；无文件大小限制 | 需两端都安装 |
| iCloud Drive | Mac 原生 | Windows 客户端慢且不稳定；免费空间仅 5GB |
| OneDrive | Windows 原生 | Mac 客户端偶尔失步；大文件有配额问题 |

### Windows 端配置

1. 下载安装：https://syncthing.net/downloads/ → 选 Windows (64-bit)
2. 启动后浏览器打开 `http://127.0.0.1:8384`
3. 点击 **Add Folder**：
   - Folder Path: `D:\AI-Content-Hub\content-store`
   - Folder Label: `AI-Content-Hub content-store`
4. 记录本机 **Device ID**（界面右上角 → Actions → Show ID）

### Mac 端配置

1. 安装：
   ```bash
   brew install syncthing
   brew services start syncthing
   ```
2. 浏览器打开 `http://127.0.0.1:8384`
3. 点击 **Add Remote Device**，填入 Windows 的 Device ID
4. Windows 端会弹出确认提示，同意后两端建立连接
5. 在 Mac 端接受共享的文件夹，设置本地路径：
   ```
   /Users/carson/workspace/ai-content-hub/workspace/content-store
   ```

### Ignore Patterns（Syncthing 文件夹设置中填入）

```
*.log
__pycache__
*.pyc
```

---

## 发布引擎（ADB）

`publish_engine_v40.sh` 已支持跨平台，Windows 和 Mac 均可运行。

### Mac 上的 adb 安装

```bash
# 方式一：Android SDK（推荐，已有 Android Studio 时）
# adb 通常在 ~/Library/Android/sdk/platform-tools/

# 方式二：Homebrew
brew install android-platform-tools
```

脚本启动时会自动检测平台并设置 adb PATH，无需手动配置。

---

## 两端职责分工

| 功能 | Windows | Mac |
|------|---------|-----|
| AI 内容生成（文本/图片/视频） | ✅ 主力运行 | ✅ 可运行 |
| 得物 ADB 自动发布 | ✅ | ✅（需 USB 连接 Android 手机） |
| 内容审核查看 | ✅ | ✅ 通过 Syncthing 实时同步 |
| 素材上传（inbox） | ✅ 直接拖入 | ✅ Syncthing 同步到 Windows |
| 归档内容查阅（archive） | ✅ | ✅ 同步查看 |

---

## 同步后的目录关系

```
Windows:                                            Mac (Syncthing 同步):
D:/AI-Content-Hub/content-store/            ←→     ~/workspace/ai-content-hub/workspace/content-store/
├── inbox/                                          ├── inbox/
├── Pending_Content/                                ├── Pending_Content/
└── archive/                                        └── archive/

代码（GitHub 同步）:
D:/AI-Content-Hub/                          ←→     ~/workspace/ai-content-hub/
├── middleware/                                     ├── middleware/
├── publish-engine/                                 ├── publish-engine/
└── docs/                                           └── docs/
```

---

## 注意事项

1. **archive/ 目录较大**：发布后内容逐渐积累，Syncthing 默认全量同步。Mac 存储有限时，可将 `archive/` 设为单向同步（Windows→Mac，Mac 不反向写入）。

2. **inbox/ 双向同步**：素材可从 Mac 拖入 inbox，Syncthing 自动同步到 Windows 供中间件处理。

3. **同一局域网时**：Syncthing 走局域网直连，图片同步通常在 1-2 秒内完成。

4. **不在同一网络时**：Syncthing 通过中继服务器同步，大文件（视频）可能有延迟。
