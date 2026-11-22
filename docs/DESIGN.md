# 明白办事 · 设计说明

## Design Read

Reading this as: a civic policy tool for community workers and residents, with an editorial public-service language, leaning toward a paper-and-ink system with one vermilion accent.

这是一个政策办事工具，不是通用 AI 聊天产品。视觉需要传达可信、可读、可核对，而不是「又一个深色渐变 AI 网站」。

## 设计方向

- Vibe：Civic Editorial。冷纸色、墨绿文字、朱砂红单一强调色、细微纸张纹理。
- Layout：Editorial Split Hero + Asymmetrical Bento 问题区 + 双栏工作台。
- Dials：DESIGN_VARIANCE 7 / MOTION_INTENSITY 5 / VISUAL_DENSITY 5。
- 主题：单一浅色主题，不做整页深浅反转。

## 视觉 Tokens

| Token | 值 | 用途 |
| --- | --- | --- |
| Paper | `#F2F0E9` | 页面底色，冷纸感 |
| Card | `#FBFAF5` | 卡片内层 |
| Ink | `#17211B` | 主文字、主按钮 |
| Ink 2 | `#39433C` | 正文 |
| Muted | `#5E665D` | 次要说明 |
| Accent | `#B5432C` | 印章、引用、强调 |
| Accent Soft | `#F2DCD3` | 提示、勾选、引用底色 |
| Sage | `#4E5C49` | 辅助状态 |

字体：

- 展示：Noto Serif SC / Source Han Serif SC / Songti SC / SimSun。
- 正文：Noto Sans SC / Source Han Sans SC / Microsoft YaHei UI / PingFang SC。
- UI 数字：Bahnschrift。
- 代码：Cascadia Code / Consolas。

字体全部走系统已安装或回退栈，不依赖外部字体 CDN。生产环境如果要跨平台一致，建议自托管 Geist / Noto 字体子集。

## 组件规则

### Double-Bezel

所有主卡片使用外层壳 + 内层芯：

- 外层：低对比底色、半透明墨色 hairline、大圆角、柔和墨绿阴影。
- 内层：纸白背景、更小同心圆角、顶部内高光。

主工作台、问题卡、案例卡和明白卡都遵循这个结构。小卡片用内嵌高光和 hairline 做轻量版本。

### CTA

主按钮是 ink pill，右侧箭头放在独立圆形内。hover 时按钮轻微上浮，箭头圆向右上移动并放大，active 时缩到 0.98。

### 形状

- 大卡片：2rem。
- 内层：1.62rem。
- 小卡片：1.2rem。
- 按钮和状态：999px pill。
- 输入区：1.1rem 到 1.3rem。

这是一套有明确规则的混合圆角系统，不做随机圆角。

## 动效

- 统一使用 `cubic-bezier(0.32, 0.72, 0, 1)`。
- 滚动入场：opacity 0 → 1，translateY 1.8rem → 0，blur 4px → 0，约 0.9s。
- 导航浮岛：桌面是顶部悬浮 pill，移动端汉堡线旋转成 X，菜单全屏展开，链接错峰滑入。
- 芯片 / 按钮：只在 transform 和 opacity 上做动效。
- 引用跳转：打开对应 `<details>`，用 opacity 覆盖层闪一下，不修改布局属性。
- `prefers-reduced-motion` 下关闭所有过渡和卡片的旋转 / 位移。

## 响应式

- 1440px：双栏 hero、双栏工作台、右侧问答面板 sticky。
- 900px：导航折叠，hero 单列，问题区单列。
- 768px：取消卡片旋转和重叠，工作台单列，卡片全宽，页面左右 1.25rem。
- 390px：政策选择器和模式切换占满一行，聊天面板静态排列。

已通过 Edge CDP 在 1440px 与 390px 下验证：没有横向溢出；移动端 nav-links 隐藏、menu-toggle 显示；hero 卡片旋转为 none。

## 可访问性

- 单一浅色主题，正文和按钮对比度满足 WCAG AA。
- 所有交互控件有可见 focus ring。
- 聊天区 `aria-live="polite"`，上传状态 `role="status"`。
- 跳过导航链接、键盘 Esc 关闭移动菜单、焦点返回。
- 材料清单使用原生 checkbox，可键盘操作。
- 大字模式放大卡片和聊天字号。
- 朗读使用浏览器 `speechSynthesis`，失败时给出提示。
- 尊重 `prefers-reduced-motion`。

## 页面检查

- 没有 Inter / Roboto / Arial / Helvetica 等禁用字体。
- 没有 em dash 或 en dash。
- 没有高饱和大面积紫色渐变。
- 主卡片使用双边框，不是单层平面卡。
- 主 CTA 使用按钮内嵌图标圆。
- 所有区块垂直留白至少 6rem。
- 所有过渡使用自定义 cubic-bezier。
- 滚动入场使用 IntersectionObserver，没有 scroll 事件监听。
- 页面只有浅色主题，不出现中途反色。
- 移动端没有横向滚动。
- 表单、按钮、占位符对比度检查通过。
- 案例页 A4 PDF：1 页，文字在页边距内，无重叠，无替换字符。

## 已知取舍

- 没有使用真实照片或生成图片。这个产品的核心是政策文本和办事卡，图片会增加噪声；纸张纹理、印章和排版承担视觉叙事。
- 没有引入 React / Tailwind 构建链，保证离线环境零构建可跑。
- 字体使用本机 Noto 字体和系统回退；跨平台一致性需要自托管字体子集。
