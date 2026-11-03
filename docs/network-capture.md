# 真实网络捕获状态

**当前状态：尚未取得真实保存请求的网络记录。** 仓库里的 `offline-reproduction.json` 和 `original-local-probe.json` 都是本地控制实验。

2026-11-03 的尝试：

1. 在真实 ima 设置页尝试打开开发者工具，页面提示组织策略禁止在此页面使用。
2. 打开该应用内置的 `chrome://net-export/`，确认界面提供原始字节记录选项。
3. 尚未启动日志记录或提交抓包用配置时，Mac 进入锁屏，UI 操作被停止。

没有修改开发者工具策略、安装根证书、设置中间人代理、改变 TLS 校验或重启应用。后续观察需要先解锁 Mac。

## 计划记录的最小实验

使用无权限的假 Key，模型为 `group/deepseek-v4-1-flash`，完整接口为 `http://127.0.0.1:3425/v1/chat/completions`。在真实保存操作前开启日志、返回后立即停止。保留目标请求的时间、URL、方法、假 Key 请求体、响应状态及错误内容，并关联对应日志 source/stream ID。

原始 NetLog 可能含账号 cookie、票据和其他窗口的流量，保留在本地受限目录。公开材料应由可复现的提取程序只选取目标请求；清楚列出省略字段、原日志哈希、事件索引和解码步骤。原始敏感日志不能直接作为公开附件。

如果抓包只能证明请求目标而没有取得 body 或响应，应分别标注，不补写缺失内容。保存的 HTTP 响应也不能单独证明服务器的长期存储方式。

工具依据：[Chromium NetLog](https://www.chromium.org/developers/design-documents/network-stack/netlog/)、[官方采集说明](https://new.chromium.org/for-testers/providing-network-details/)。
