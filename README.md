<div align="center">

# astrbot_plugin_groupsays

_✨ 把群友 + 一段话 渲染成 my_friend 风格的聊天气泡表情包 ✨_

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-%E2%89%A54.5-orange.svg)](https://github.com/AstrBotDevs/AstrBot)
[![Platform](https://img.shields.io/badge/Platform-aiocqhttp%20%2F%20OneBot%20v11-lightgrey)](https://github.com/AstrBotDevs/AstrBot)
[![GitHub](https://img.shields.io/badge/Repo-Catkamakura%2Fastrbot__plugin__groupsays-brightgreen)](https://github.com/Catkamakura/astrbot_plugin_groupsays)

</div>

---

## 💡 介绍

`/群友说 @某人 牛逼`，自动生成下面这种聊天截图风格的表情包：

```
[圆形头像]   群友昵称
            ┌──────────┐
            │   牛逼   │
            └──────────┘
```

两个入口都通向同一个渲染管线：

1. **斜杠命令** —— `/群友说 @某人 要说的话`
2. **LLM 函数调用** —— 用户对 LLM 自然语言说"帮我做 张三 说『睡了』的表情包"，LLM 会自动调用 `generate_groupsays_meme` 工具，按昵称模糊匹配到群友 QQ 号再生成

支持权限层（白名单 / 豁免 / 反弹反击）。

> **平台**：仅支持 `aiocqhttp`（NapCat / OneBot v11）。其他平台没有等价的"群成员头像 / 昵称"API。

## 📦 安装

> 本插件**不在 AstrBot 插件市场**（作者没空走 human review 流程），请用以下任一方式手动安装。装完都需要在 AstrBot 控制台 / WebUI **重载插件**或重启 AstrBot 才会生效。

### 方式 1 · WebUI 安装（推荐）

1. 打开 AstrBot 管理面板 → **插件管理** → **安装插件**
2. 选择 **"从 URL 安装"**，粘贴：
   ```
   https://github.com/Catkamakura/astrbot_plugin_groupsays
   ```
3. 等待克隆完成。WebUI 会自动 pip 安装 `requirements.txt`。

### 方式 2 · 聊天命令安装

在 AstrBot 能监听的群聊或私聊里（管理员账号）发送：

```
/plugin i https://github.com/Catkamakura/astrbot_plugin_groupsays
```

### 方式 3 · 手动 git clone

适合喜欢自己 pull / 改代码的用户。在 AstrBot 的 data 目录下：

```bash
cd <astrbot-data>/plugins/
git clone https://github.com/Catkamakura/astrbot_plugin_groupsays.git
pip install -r astrbot_plugin_groupsays/requirements.txt
# 然后在 WebUI 里点重载插件，或重启 AstrBot
```

> `<astrbot-data>` 视部署方式而定：Docker 是 `astrbot-data` 卷挂载点（容器内 `/AstrBot/data`），裸装是 AstrBot 安装目录下的 `data/`。

### 升级 / 更新

- **方式 1 / 2**：在 WebUI 插件管理点更新即可
- **方式 3**：`cd astrbot_plugin_groupsays && git pull` 后重载

### 字体说明

首次渲染会自动从 Adobe 官方仓库下载思源黑体 CN（约 11MB）作为兜底字体。如果不希望联网下载或想用别的字体，把任意 `.ttf` / `.otf` / `.ttc` 文件放到 `<plugin_dir>/fonts/`，插件会优先使用。详见下方 [🎨 自定义字体](#-自定义字体)。

## ⚙️ 配置

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `max_nickname_length` | `20` | 群昵称最大长度，超出截断 |
| `max_text_length` | `200` | 正文最大长度，超出截断 |
| `strip_emoji_in_nickname` | `true` | 清除昵称里的 emoji（避免渲染成 □） |
| `exemption_list` | `""` | 豁免名单（QQ 号逗号分隔），名单里的人不能被生成 |
| `whitelist` | `""` | 白名单（QQ 号逗号分隔），无视豁免限制 |
| `counter_attack` | `false` | 反弹反击：对豁免成员使用时改为生成『命令发起者』自己 |
| `counter_attack_text` | `""` | 反击时附加在文本前的固定前缀（可选） |
| `bubble_bg` | `#FFFFFF` | 气泡颜色 |
| `canvas_bg` | `#E4E8F0` | 画布背景色（≈ QQ 默认聊天页背景） |

权限优先级（在豁免冲突时）：

```
白名单 > 豁免 > 反弹反击
```

也就是说白名单用户即便对豁免成员动手也能生成；普通用户碰到豁免成员要么被拒，要么（开启反击时）反弹回自己。

## ⌨️ 使用

### 1. 直接命令

```
/群友说 @某人 你刚说什么
```

- 多个 `@` 只取**第一个**
- 仅支持文本正文，会先做一轮昵称 / 正文清洗（去 zero-width / bidi / control char，可选去 emoji）

### 2. 让 LLM 调用

把一段自然语言交给 LLM，它会自己挑工具：

> 帮我生成 张三 说"我先睡了"的表情包  
> 做一张 老王 说"鼠鼠我啊" 的群友说

LLM 收到名字后用 `get_group_member_list` 在群里做模糊匹配（精确 → 前缀 → 子串，同名取最短），再按 QQ 号走相同的渲染管线。

## 🎨 自定义字体

把任意 `.ttf` / `.otf` / `.ttc` 文件放到 `<plugin_dir>/fonts/`，插件会优先使用。

字体优先级：

1. `<plugin_dir>/fonts/` 下的任意字体文件
2. 系统 Noto CJK / WenQuanYi / PingFang / Microsoft YaHei
3. 自动从 Adobe 官方仓库下载思源黑体 CN（兜底）

推荐字体：

- [LXGW WenKai 霞鹜文楷](https://github.com/lxgw/LxgwWenKai)
- [Smiley Sans 得意黑](https://github.com/atelier-anchor/smiley-sans)
- [阿里巴巴普惠体 3.0](https://fonts.alibabagroup.com/)

## 🎁 主题（实验性 · `qq-bubble` 分支）

把 QQ 任意一张气泡图（或 Android `.9.png`）转成插件能用的主题。

### 1. 准备一张气泡图

来源（按"自动化程度"排序）：

| 来源 | 自动程度 | 备注 |
|---|---|---|
| **Android `.9.png`** | 100% | Android Studio 的 9-patch tool 拖出 marker 边界，一次到位 |
| **QQ APK 解包后的 `.9.png`** | 100% | 用 `apktool` / `unzip` 解 APK，找 `res/drawable-*/` 下的 `.9.png` |
| **普通气泡 PNG（截图、网图、自己画的）** | 70-80% | 用启发式自动找 9-slice 边角；有时需要手调 manifest |

### 2. 跑导入器

```bash
cd <plugin_dir>

# .9.png（精确）
python -m tools.import_theme path/to/bubble.9.png mytheme

# 普通 PNG（启发式）
python -m tools.import_theme path/to/bubble.png mytheme

# 想批扫一个目录看哪些 PNG 像气泡（不写文件）
python -m tools.import_theme path/to/apk_unzip/ --scan

# 看检测结果不写文件
python -m tools.import_theme bubble.png mytheme --dry-run

# 写到不同目录
python -m tools.import_theme bubble.png mytheme --out /path/to/themes
```

输出（默认 `./themes/<name>/`）：

```
themes/mytheme/
├── manifest.json    # 9-slice padding + content padding + 文字色
└── body.png         # 气泡本体
```

### 3. 启用

把上面那个目录放到下面任一位置：

- `<astrbot-data>/plugins/astrbot_plugin_groupsays/themes/<name>/`（用户层，推荐）
- `<plugin_dir>/themes/<name>/`（捆绑层）

然后在 AstrBot 的插件配置里把 `theme` 字段填成 `<name>` —— 立即生效，下次 `/群友说` 就用新气泡了。

### 4. manifest.json 字段

```json
{
  "name": "MyTheme",
  "body": "body.png",
  "padding_9slice":  [top, left, bottom, right],
  "padding_content": [top, left, bottom, right],
  "text_color": "#000000",
  "min_size": [w, h]
}
```

- `padding_9slice` —— 4 个角不缩放区域的像素数。9-slice 缩放时，这 4 块固定，剩下的边缘和中心被拉伸
- `padding_content` —— 文字相对气泡边的内边距。一般等于或略大于 `padding_9slice`
- `text_color` —— 文字颜色（覆盖 `BUBBLE_FG` 默认黑）
- `min_size` —— 气泡最小尺寸（可选，0 表示无下限）

启发式产出的 padding 不准时直接编辑这里，重启插件即可。

### 已知局限

- **启发式 9-slice 检测**对带渐变 / 噪点的气泡可能误判（落到 4px 下限），需要手编 manifest
- **不解 Tencent 自家加密素材包**（`.zpkg` / `.skin` 这种）。能用的只是从 APK 直接 dump 出来的明文 `.png` / `.9.png`
- **本分支（qq-bubble）尚未 merge 到 main**，要用得 `git checkout qq-bubble` 或在 v0.3 release 之后再升级

## 🛠️ 开发

```
astrbot_plugin_groupsays/
├── main.py              # @register 入口，命令 + LLM tool + pipeline
├── utils.py             # 消息解析 + 昵称/正文清洗（NFKC、去 zero-width 等）
├── render.py            # Pillow 图片合成（圆形头像、气泡 + 尾巴、CJK 换行）
├── fonts.py             # 字体发现 / 系统候选 / 首次下载
├── metadata.yaml
├── requirements.txt
├── _conf_schema.json
└── fonts/               # 用户字体覆盖（默认空）
```

依赖：`Pillow >= 10`、`httpx >= 0.25`、AstrBot `>= 4.5`。

## 📜 更新日志

### v0.2.2

- 修复单字（如 `草` / `?`）渲染成 170px 宽的"长方形"问题；现在按文本长度自适应宽度
- 整体重新校准成真实 QQ 比例：avatar 96 → 56，正文字号 32 → 28，昵称字号 22 → 16，等
- 修复 `command_aliases` 配置实际未生效（已从 schema 删除）
- README 重写为 AstrBot 社区风格 header + 完整命令矩阵 + 故障排查
- `metadata.yaml` 升级到 v4.5+ 标准（`display_name` / `astrbot_version` / `support_platforms`）

### v0.2.1

- 加入豁免 / 白名单 / 反弹反击三层权限
- 加 `generate_groupsays_meme` LLM tool 入口
- 头像 / 昵称并行抓取

### v0.1.0

- 首版：基础 `/群友说 @某人 文本` → 渲染输出

## 📄 License

MIT
