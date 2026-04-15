# astrbot_plugin_groupsays

轻量"群友说"表情包生成器 — `@某人 + 一段话` → 生成 my_friend 风格的聊天气泡图。

目前仅适配 **NapCat / OneBot v11**。

## 用法

### 1. 斜杠命令

```
/群友说 @某人 要说的话
```

多 @ 只取第一个。仅支持文本正文。

### 2. LLM 自然语言调用

工具 `generate_groupsays_meme` 会自动注册给 LLM，用户可以直接说：

- "帮我生成一个 小明 说"牛逼"的表情包"
- "做一张 张三 说"我先睡了" 的群友说"

LLM 会自动把名字 → QQ 号（模糊匹配群成员列表）并调用工具。

## 豁免与反击

- **豁免列表**：在配置里填 QQ 号（逗号分隔），这些人不会被生成。
- **反击功能**：开启后，对豁免列表成员使用时，会**反弹到命令发起者**，生成「发起者说 XXX」的表情包。

## 特性

- 圆形头像 + 群昵称（自动通过 OneBot `get_group_member_info` 查询）
- 昵称清洗：移除 emoji、零宽字符、双向控制字符等"逆天昵称"
- CJK 友好的逐字换行
- 正文最多 200 字（可配置）
- 首次使用自动下载字体（思源黑体 CN Regular, ~11MB），后续缓存

## 配置

在 AstrBot 面板的插件管理 → 本插件 → 编辑配置：

| 配置项 | 默认 | 说明 |
|---|---|---|
| `max_nickname_length` | 20 | 群昵称最大长度 |
| `max_text_length` | 200 | 正文最大长度 |
| `strip_emoji_in_nickname` | `true` | 清除昵称中的 emoji |
| `command_aliases` | `群友说` | 命令别名，逗号分隔 |
| `bubble_bg` | `#FFFFFF` | 气泡颜色 |
| `canvas_bg` | `#EBEBEB` | 画布颜色 |

## 自定义字体

默认会自动下载思源黑体。如需手动指定字体：

把任意 `.ttf` 或 `.otf` 文件放到插件目录的 `fonts/` 下即可（会优先使用）。

推荐字体：
- [LXGW WenKai](https://github.com/lxgw/LxgwWenKai)
- [Smiley Sans 得意黑](https://github.com/atelier-anchor/smiley-sans)
- [阿里巴巴普惠体 3.0](https://fonts.alibabagroup.com/)

## 开发

```
astrbot_plugin_groupsays/
├── main.py           # 插件入口
├── utils.py          # 昵称清洗 + 事件解析
├── render.py         # 图片合成
├── fonts.py          # 字体发现 / 下载
├── metadata.yaml
├── requirements.txt
├── _conf_schema.json
└── fonts/            # 自定义字体目录
```

## TODO

- [ ] 支持"回复某人 + 文本"不 @ 的用法
- [ ] 多 At 轮流说话（对话截图风格）
- [ ] 多模板（举牌、看板娘）
- [ ] emoji 彩色渲染（pilmoji）

## License

MIT
