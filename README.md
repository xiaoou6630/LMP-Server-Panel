# ML Server Manager

KSP（坎巴拉太空计划）多人联机服务端管理工具，基于 Web 界面管理 LMP（Luna Multiplayer）服务器配置、模组名单和服务器运行状态。

## 功能特性

- **配置编辑器** - 可视化修改 LMP 服务器配置（服务器名称、端口、玩家数量等）
- **模组管理** - 管理 CKAN 模组列表，支持黑白名单模式
- **服务器控制** - 一键启动/停止/重启 LMP 服务端
- **实时日志** - 在网页中查看服务器运行日志
- **系统托盘** - 最小化到系统托盘，后台运行

## 快速开始

### 开发环境

```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 安装依赖
venv\Scripts\pip install -r requirements.txt

# 3. 启动服务
venv\Scripts\python run.py

# 4. 浏览器访问 http://127.0.0.1:8080
```

### 打包

```bash
# 使用虚拟环境打包
venv\Scripts\python build_scripts\build.py
```

打包完成后在 `release/` 目录下找到 `ML_Server_Manager.exe`。

## 技术栈

- **后端**: Python 3.10+, FastAPI, uvicorn
- **前端**: HTML + CSS + Vue.js (CDN)
- **打包**: PyInstaller

## 目录结构

```
ML/
├── backend/           # 后端代码
│   ├── main.py        # FastAPI 应用入口
│   ├── config.py      # 应用配置管理
│   ├── config_editor.py  # LMP 配置文件编辑器
│   ├── server_manager.py # LMP 服务器管理
│   ├── mod_list_manager.py # 模组名单管理
│   ├── ckan_manager.py   # CKAN 模组管理
│   └── ...
├── frontend/          # 前端页面
│   └── index.html
├── build_scripts/     # 打包脚本
│   └── build.py
├── tools/             # 第三方工具（LMP、CKAN）
├── data/              # 数据存储
├── requirements.txt   # Python 依赖
└── run.py             # 启动脚本
```

## 注意事项

- 修改配置后需重启服务器才能生效
- LMP 服务端文件位于 `tools/lmp_server/LMPServer/`
- 关闭服务器时请用 Ctrl+C 确保存档备份

## 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE) 文件。

## 作者

xiaoou6630
