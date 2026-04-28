# Clash Config Parser 操作文档

## 项目结构

```
clash-config-parser/
├── clash_config_parser/
│   ├── app.py              # Flask 入口，路由注册
│   ├── constants.py        # 所有常量（节点、规则、TUN 配置等）
│   ├── parsers.py          # 协议解析（hysteria2, vmess, vless, trojan, ss）
│   ├── converter.py        # YAML 转换逻辑（清理节点、注入规则、负载均衡等）
│   ├── region_filter.py    # 节点地区筛选
│   ├── config_store.py     # 配置源持久化（读写 data/configs.json）
│   ├── rules_store.py      # 规则文件管理（读写 config/rules.txt + 文件监控）
│   ├── cache.py            # Redis + 内存缓存
│   ├── auth.py             # 管理界面密码认证
│   ├── templates/          # 管理界面模板
│   └── static/             # 前端样式与逻辑
├── config/
│   └── rules.txt       # 自定义路由规则
├── data/
│   └── configs.json    # 配置源数据（自动生成，勿手动编辑）
├── downloads/          # 公开托管文件
│   ├── Country.mmdb
│   ├── geosite.dat
│   ├── mihomo-linux-amd64-v3-v1.19.18.deb
│   └── mihomo-linux-arm64-alpha-56c3462.gz
├── tools/
│   └── test_converter.py   # 本地 CLI 测试工具
├── requirements.txt    # Python 依赖
├── Dockerfile
└── docker-compose.yml
```

## 快速启动

```bash
# Docker 一键启动（推荐）
docker compose up --build -d

# 查看日志
docker compose logs -f app
```

服务启动后：
- 管理界面：`http://<IP>:8200/`
- 管理密码：在 `docker-compose.yml` 的 `ADMIN_PASSWORD` 中设置

## 敏感配置

不要把订阅 URL、订阅 token、专线节点、UUID 等写进 Python 文件或提交到 GitHub。配置源会保存在已忽略的 `data/configs.json`，推荐通过管理界面添加；VIP 专线节点如需启用，用环境变量 `VIP_NODE_JSON` 注入。

首次启动也可以用 `DEFAULT_CONFIGS_JSON` 初始化配置源：

```bash
DEFAULT_CONFIGS_JSON='{"my-config":{"url":"https://example.com/subscribe","type":"yaml","enable_vip":false}}'
```

VIP 节点示例：

```bash
VIP_NODE_JSON='{"name":"VIP","type":"vless","server":"example.com","port":443,"uuid":"REPLACE_ME"}'
```

## 管理界面使用

### 登录
访问 `http://<IP>:8200/`，输入管理密码登录。

### 配置管理（第一个 Tab）
- **添加配置**：点击"添加配置"按钮，填写名称、订阅 URL、类型
- **编辑配置**：点击对应行的"编辑"按钮
- **删除配置**：点击"删除"按钮
- **复制链接**：点击"复制链接"获取该配置的转换 URL，粘贴到 Clash 客户端使用
- **清除缓存**：清除所有已缓存的远程配置

配置选项说明：
| 选项 | 说明 |
|------|------|
| 类型 YAML | 远程源是标准 Clash YAML 格式 |
| 类型 Base64 | 远程源是 Base64 编码的订阅链接 |
| 跳过规则 | 不注入 config/rules.txt 中的自定义规则，只保留 DIRECT 基础规则 |
| HF 负载均衡 | 启用 HuggingFace 多通道负载均衡，自动选取港日新专线节点轮询下载 |
| 节点地区 | 可选择只保留或排除指定地区节点，例如日本、美国 |

### 规则编辑（第二个 Tab）
- 直接编辑 `config/rules.txt` 内容
- 每行一条规则，格式：`TYPE,DOMAIN,策略组`
- `#` 开头的行为注释
- 点击"保存规则"后立即生效（自动清除缓存）

### 文件托管（第三个 Tab）
- 复制 `geosite.dat`、`Country.mmdb` 和 mihomo 安装包的公开下载链接
- 复制自动下载命令，目标机器会按 `uname -m` 自动选择 amd64 或 arm64
- 脚本会把 `mihomo`、`geosite.dat`、`Country.mmdb` 保存到执行命令时所在的当前目录
- 点击每个托管文件行的"更新文件"，可以从浏览器上传新文件并覆盖当前托管版本

常用下载命令：

```bash
wget http://<IP>:8200/downloads/geosite.dat
wget http://<IP>:8200/downloads/Country.mmdb
wget http://<IP>:8200/downloads/mihomo/amd64 -O mihomo-amd64.deb
wget http://<IP>:8200/downloads/mihomo/arm64 -O mihomo-arm64.gz
```

一键下载到当前目录：

```bash
wget -O - http://<IP>:8200/install/mihomo.sh | sh
wget -O - http://<IP>:8200/install/mihomo-amd64.sh | sh
wget -O - http://<IP>:8200/install/mihomo-arm64.sh | sh
```

## API 接口

### 公开接口（无需认证）

| 接口 | 说明 |
|------|------|
| `GET /convert?config=<名称>` | 获取转换后的 Clash 配置 |
| `GET /convert?config=<名称>&tun=true` | 启用 TUN 模式 |
| `GET /convert?config=<名称>&load_balance=true` | 手动启用负载均衡 |
| `GET /convert?config=<名称>&region_mode=include&regions=jp,us` | 临时只保留指定地区节点 |
| `GET /downloads/<文件名>` | 下载托管文件 |
| `GET /downloads/mihomo/amd64` | 下载 amd64 mihomo Debian 包 |
| `GET /downloads/mihomo/arm64` | 下载 arm64 mihomo gzip 二进制 |
| `GET /install/mihomo.sh` | 自动识别架构并下载到当前目录的脚本 |
| `GET /health` | 健康检查 |

### 管理接口（需认证）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/configs` | GET | 列出所有配置 |
| `/api/configs` | POST | 添加配置 `{"name":"x","url":"..."}` |
| `/api/configs/<名称>` | PUT | 修改配置 |
| `/api/configs/<名称>` | DELETE | 删除配置 |
| `/api/rules` | GET | 获取规则内容 |
| `/api/rules` | PUT | 保存规则 `{"content":"..."}` |
| `/api/downloads` | GET | 列出托管文件和安装脚本 |
| `/api/downloads/<文件名>` | POST | 上传并覆盖指定托管文件（multipart 字段名 `file`） |
| `/api/clear-cache` | POST | 清除缓存 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_PASSWORD` | 空（无密码） | 管理界面登录密码 |
| `SECRET_KEY` | 随机生成 | Flask session 密钥 |
| `DEFAULT_CONFIGS_JSON` | 空 | 首次生成 `data/configs.json` 时使用的配置源 JSON |
| `VIP_NODE_JSON` | 空 | AI 专线 VIP 节点 JSON；为空时跳过 VIP 节点注入 |
| `REDIS_URL` | 空 | Redis 连接地址，设置后启用 Redis 缓存 |
| `CACHE_TTL_SECONDS` | 300 | 缓存过期时间（秒） |
| `RULES_SCAN_INTERVAL` | 15 | config/rules.txt 变更检测间隔（秒） |
| `HOSTED_FILE_MAX_MB` | 256 | 前端上传托管文件的最大体积 |

## 数据持久化

- `data/configs.json`：配置源数据，首次启动时从代码默认值自动生成
- `config/rules.txt`：路由规则文件，可通过管理界面或直接编辑
- `downloads/`：公开托管文件和 mihomo 安装包

Docker 部署时这些路径已通过卷挂载持久化，容器重建不会丢失数据。

## 本地开发

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m clash_config_parser.app    # 启动开发服务器，端口 5000
```

## CLI 测试工具

```bash
python tools/test_converter.py <输入文件.yml> [输出文件.yml] [--tun]
```
