<br />

# KSP开服器 (KS-1) 完整技术规范 v4.0 (最终版)

> **开发原则**：
>
> 1. 对于任何功能点，如果网络资料不足或存在歧义，**必须直接查阅 LMP 或 CKAN 的官方源代码**（GitHub 仓库），以源码行为为准。
> 2. 所有代码完成后，**必须删除测试代码**，不留安全隐患。
> 3. 不直接分发 LMP、CKAN 或任何非 MIT/BSD 许可证的二进制文件。用户手动放入 `lib` 文件夹。
> 4. **模组管理核心**：服务器端只维护一个“允许/禁止模组名单”（即 LMP 的 `ModControl.xml` 或类似机制），不下载、不安装模组实体文件。CKAN 仅用于搜索模组信息和导出 `.ckan` 元数据文件。

***

## 一、项目概述

开发一个 **坎巴拉太空计划（KSP）LMP（Luna Multiplayer）服务器管理器**，具备：

- 现代化 Web 前端（浏览器访问）
- Python 后端（Flask + pystray 系统托盘）
- 模组名单管理（基于 CKAN 仓库搜索模组，管理允许/禁止列表，导出兼容 CKAN 的 `.ckan` 元数据文件）
- QQ 机器人通知与查询（NoneBot2，反向 WebSocket，无公网 IP）
- 安全纵深防御（RSA+AES 加密、指令白名单、HTTP Basic Auth、降权运行等）

技术栈：

- 前端：HTML5/CSS3/JS (ES6)，无框架，Font Awesome 6，免费开源字体 Inter（tuna CDN）
- 后端：Python 3.11，Flask，Flask-CORS，pystray，Pillow，cryptography，bcrypt，waitress
- 机器人：nonebot2，nonebot-adapter-qq（或 go-cqhttp 反向 WS），httpx
- 打包：**使用** **`build.py`** **脚本**（PyInstaller 封装）生成单个 `kspp.exe` 文件
- 通信：RSA + AES-256-GCM 混合加密，WebSocket 用于终端实时输出

***

## 二、前端详细要求

### 2.1 全局样式与交互

- 圆角：`border-radius: 6px`
- **暗色模式**：主题色黑色 `#0A0A0A`，深灰色 `#1E1E1E`，选中色蓝色 `#0078D4`，白色字 `#FFFFFF`
- **亮色模式**：主题色白色 `#FFFFFF`，选中色蓝色 `#0078D4`，黑色字 `#000000`
- 字体：Inter，从 `https://mirrors.tuna.tsinghua.edu.cn/github-release/rsms/inter/` 加载或使用 Google Fonts 备用
- 响应式：支持 1920x1080 及以下，侧边栏可折叠（折叠宽度 64px，展开 240px）

### 2.2 侧边栏

- 左上角：软件图标（Font Awesome 6 的 `fa-rocket` 或自定义 SVG）
- 菜单项（从上到下）：
  1. 服务器状态
  2. 服务器设置
  3. **模组名单管理**（原“服务器模组管理”改名，强调只管理名单）
  4. 设置
- 底部：收起/展开按钮（`fa-chevron-left` / `fa-chevron-right`）
- 收起时只显示图标，展开时显示图标+文字

### 2.3 服务器状态页

- **顶部栏**：左侧显示“服务器状态”标题，右侧显示运行状态徽章（绿色/灰色）+ 开关服务器按钮（蓝色）
- **玩家数显示**：
  - 卡片或横条，**左侧显示当前在线玩家数量**，**右侧显示服务器支持的总玩家数**，格式 `3 / 16`
  - 实时刷新：每秒随 CPU/内存数据一起更新（通过 `/api/stats` 长轮询）
  - 使用较大字体，附加玩家图标（`fa-users`）
- **CPU 占用条**：
  - 三段式：其他占用、kspp 占用、服务器占用，总和 100%
  - 下方数字：系统总 CPU% / kspp CPU% / LMP CPU% / 其他%
  - 每秒刷新一次
- **内存占用条**：
  - 三段式：其他内存、服务器内存、kspp 占用，总上限为系统物理内存
  - 下方数字：已用/总量，细分数值（MB/GB）
- **终端窗口**：
  - 黑色背景，绿色/白色等宽字体，显示 LMP 控制台实时输出
  - 底部输入框 + 发送按钮
  - **指令白名单机制**：只允许白名单内的 LMP 指令（如 `/help`, `/players`, `/kick`, `/ban`, `/unban`, `/stop`, `/start`, `/say`, `/motd`, `/admin`）
  - 输入框支持历史命令（上下键）
  - 连接方式：WebSocket（`/ws/terminal`）推送日志和接收命令

### 2.4 服务器设置页

分为两个折叠面板：**基础设置**、**黑/白名单管理**

#### 2.4.1 基础设置

**必须完整映射 LMP 的所有配置项**，Agent 需查阅 LMP 源码中的 `Settings` 类。至少包括：

- 服务器名称、密码、管理员密码
- 最大玩家数（number，1-128）—— **与状态页总玩家数联动**
- 端口、心跳间隔、MTU
- 游戏模式（Sandbox/Career/Science）
- 难度（Easy/Normal/Moderate/Hard/Custom）
- 是否允许作弊、是否启用模组控制、同步间隔、记录聊天、强制沙盒等

**每个输入框/开关旁边必须有问号图标（`fa-question-circle`）**，悬停显示解释。

**输入验证**：无效输入边框变红，有错误提示。

**保存按钮**：写入 LMP 配置文件，尝试热重载或提示重启。

**打开存档位置按钮**：调用 `/api/open-saves`，后端用系统文件管理器打开。

#### 2.4.2 玩家黑/白名单管理

- 若 LMP 原生支持，直接读写；否则自行实现（存储 JSON 文件，玩家连接时拦截）。
- 界面：下拉选择模式（无名单/白名单/黑名单），列表显示玩家名/ID，支持添加、删除、导入/导出 JSON。

### 2.5 模组名单管理页（重点修改）

> **核心变化**：服务器端不下载、不安装任何模组实体文件。只管理“允许哪些模组被客户端使用”（即 LMP 的模组控制列表，如 `ModControl.xml`，定义 `Allow` / `Deny` / `Force` 规则）。CKAN 仅用于搜索模组信息和导出 `.ckan` 文件。

分为两个 Tab：**模组商店（搜索与添加）**、**已添加模组名单**

#### 2.5.1 模组商店（搜索与添加）

- 数据源：从 **CKAN 官方仓库**（`https://github.com/KSP-CKAN/CKAN-meta` 或 CKAN API）实时搜索。
- 后端接口：`/api/ckan/search?q=关键词&page=1`
- 列表展示：模组名称、作者、版本、简介、下载次数、依赖关系
- 每个模组旁边有 **“添加到名单”** 按钮（不下载任何文件）。
- 点击“添加到名单”时，弹出选择框：**允许（Allow）/ 禁止（Deny）/ 强制（Force）**（对应 LMP 模组控制规则）。确认后，将该模组及其规则写入 LMP 的模组配置文件中（如 `ModControl.xml`）。
- **右上角按钮：“导出 .ckan 文件”** —— 见 2.5.3

#### 2.5.2 已添加模组名单

- 显示当前已添加到 LMP 模组控制列表中的所有模组（从 `ModControl.xml` 读取）。
- 每行显示：模组名称、版本（可选）、规则（允许/禁止/强制）、操作（修改规则、从名单移除）
- 修改规则或移除时，实时更新 LMP 配置文件。
- **不需要“下载”、“安装”、“卸载”等与实体文件相关的按钮**。

#### 2.5.3 导出 .ckan 文件（自定义设置）

> **功能**：将当前“已添加模组名单”导出为一个 `.ckan` 元数据包文件（不包含任何模组文件），该文件可被官方 CKAN 客户端直接安装（安装时 CKAN 会自动从仓库下载模组）。

**完全参照 CKAN 官方源码中关于** **`.ckan`** **metapackage 的导出功能**。

**界面**（点击“导出 .ckan”按钮后弹出模态框）：

1. **元数据编辑**：
   - 标识符（identifier，必填，默认如 `my-ksp-modpack`）
   - 名称（name）
   - 简介（abstract）
   - 许可证（license，默认 `MIT`）
   - 作者（author）
   - 版本（version，如 `1.0.0`）
2. **依赖规则转换**：
   - 对于名单中的每个模组，根据其 LMP 规则自动映射到 CKAN 依赖类型：
     - `Allow` → 默认映射为 `recommends`（推荐）
     - `Force` → 映射为 `depends`（硬依赖）
     - `Deny` → 映射为 `conflicts`（冲突，表示不能一起安装）
   - 用户可以在导出前手动调整每个模组的最终依赖类型（允许覆盖）。
3. **选择导出子集**：
   - 默认勾选所有已添加模组，用户可以取消勾选某些模组不导出。
4. **生成文件**：
   - 后端按照 CKAN metapackage schema（`spec_version: "v1.18"`）构造 JSON，生成 `.ckan` 文件并提供下载。
   - 文件命名：`{identifier}-{version}.ckan`

### 2.6 设置页

- **一级密码设置**：网页内弹窗设置密码（bcrypt 哈希）。API 访问需要 Bearer token。
- **二级密码设置**：HTTP Basic Authentication（用户名 `admin`，密码独立 bcrypt 存储）。
- **亮暗色切换**：Toggle，保存到 localStorage。
- **语言切换**：中/英，i18n JSON。
- **QQ 机器人配置**：启用开关、机器人 QQ 号、管理员 QQ 号、连接状态、通知事件勾选、反向 WebSocket 地址（默认 `ws://localhost:8080/qq/ws`）。

***

## 三、后端详细要求

### 3.1 核心架构

- 入口：`kspp.py`，启动系统托盘和 Flask 应用（waitress）。
- 系统托盘：右键菜单“打开主界面”、“退出”。
- 启动时检查 `lib/lmp` 和 `lib/ckan`（可选，CKAN 只用于搜索和导出，没有也能运行但提示功能受限）。

### 3.2 加密与安全

- **RSA + AES-256-GCM 混合加密**：`/api/key` 获取公钥，前端生成 AES 密钥加密传输。
- **指令白名单**：后端检查终端命令，仅允许预设列表。
- **访问控制**：一级密码（JWT token，1 小时过期） + 二级 HTTP Basic Auth（中间件）。
- **IP 白名单**（可选）：默认 `127.0.0.1`。
- **敏感配置**：bcrypt 哈希存储。

### 3.3 LMP 管理功能

- **读取/写入配置**：Agent 查阅 LMP 源码，实现配置读写（XML/JSON）。
- **启动/停止 LMP 进程**：捕获 stdout/stderr 通过 WebSocket 广播。
- **终端命令执行**：向 LMP 进程 stdin 写入（若支持）或通过 RCon。
- **获取当前在线玩家数**：通过静默执行 `/players` 命令并解析输出，或从日志流中维护玩家列表。每秒调用一次，供 `/api/stats` 返回。

### 3.4 模组名单管理（核心修改）

- **读取 LMP 模组控制文件**：查阅 LMP 源码确定模组控制文件路径和格式（通常是 `ModControl.xml`），实现 `ModListManager` 类，提供：
  - `list_mods()` → 返回当前名单（模组 ID、规则）
  - `add_mod(mod_id, rule)` → rule 为 `Allow`/`Deny`/`Force`
  - `remove_mod(mod_id)`
  - `update_rule(mod_id, new_rule)`
- **CKAN 搜索代理**：`/api/ckan/search` 请求 CKAN 官方 API（或直接访问 `https://ckan.org/api/`），返回模组元数据（不下载任何文件）。
- **导出 .ckan**：`/api/export-ckan` 接收前端提交的元数据及模组映射列表，生成符合 CKAN metapackage schema 的 JSON 文件，响应 `application/octet-stream` 下载。

### 3.5 QQ 机器人集成

- 使用 NoneBot2 + 反向 WebSocket，监听 `ws://127.0.0.1:8080/qq/ws`。
- 命令：`/status`, `/players`, `/say`, `/stop`, `/start`，仅管理员 QQ 可用。
- 主动通知：服务器启动/停止、玩家加入/退出（可选）。

***

## 四、配置与数据存储

- 启动时创建 `config.json`，使用 **SHA256 哈希签名防篡改**（配置 + 签名文件）。
- 敏感字段（密码）存储 bcrypt 哈希。
- 目录结构：
  ```
  lib/
    lmp/            (用户手动放入 LMP 服务端)
    ckan/           (可选，用户手动放入 CKAN 命令行工具)
  modlist.json      (如果 LMP 原生不支持，自行维护的模组名单备份)
  config.json
  config.sig
  ```

***

## 五、打包：使用 `build.py`

要求编写 `build.py` 脚本，执行以下操作：

1. 清理旧的 `build/`、`dist/` 目录。
2. 删除所有测试代码（如 `test_*.py`、`*_test.py`、以及任何包含 `if __name__ == "__main__"` 的测试入口）。
3. 使用 PyInstaller 打包 `kspp.py`，参数：
   - `--onefile` 生成单个 exe
   - `--name kspp`
   - `--add-data "templates;templates"`（如有）
   - `--add-data "static;static"`
   - `--icon icon.ico`（提供默认图标）
   - `--hidden-import` 必要时添加
   - `--noconsole`（可选，隐藏控制台，但建议保留用于调试，发布时去掉）
4. 将生成的 `dist/kspp.exe` 复制到输出目录 `release/`。
5. 同时生成一个 `README.txt` 说明用户需要手动创建 `lib/lmp` 并放入 LMP 服务端。
6. 打包完成后删除中间文件（但保留 `dist/kspp.exe`）。

`build.py` 应能被直接运行（`python build.py`）完成整个打包流程。

***

## 六、测试要求

- **后端单元测试**：使用 `pytest` 测试配置读写、加密、模组名单管理（不涉及真实 LMP 进程）。
- **前端手动测试**：UI 交互、主题切换、i18n、响应式。
- **集成测试**：连接真实 LMP 服务端，测试开关服、玩家数显示、终端命令、模组名单增删改查、导出 .ckan。
- **安全测试**：尝试绕过登录、注入指令、篡改 config.json。
- **测试代码清理**：打包前删除所有测试代码（包括 `tests/` 目录、`pytest` 配置、任何 mock 文件）。

***

## 七、注意事项

- 任何不确定的地方（LMP 模组控制文件格式、是否支持 stdin 命令、黑白名单原生支持等）**必须要求 Agent 直接阅读 LMP 官方 GitHub 源码**，并在代码注释中标注来源文件和行号。
- 不要使用 `eval()` 或动态执行用户输入。
- 所有网络通信走 WSS/HTTPS（本地自签名证书）。
- 最终交付物：完整的项目源码（包含前端静态文件、后端 `.py`、`requirements.txt`、`build.py`、`README.md`）。

***

**以上为 v4.0 完整技术规范，请 AI agent 严格遵照执行。**
