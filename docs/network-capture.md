# 真实客户端网络观察与解码

**2026-11-04 已取得真实保存请求、响应及同次遥测日志中的参数。** 本页区分第一次去隐私采集和随后经用户明确授权的原始字节采集；两者均与最初的断网复现分开记录。

## 实验与原件

客户端设置页显示 `2.6.16(5304)`，日志自报 `ima.copilot 150.0.7871.5493`。每次记录中都只点击一次保存：自定义厂商、`http://127.0.0.1:3425/v1/chat/completions`、`group/deepseek-v4-1-flash`，以及无权限的测试 Key，值见[UI 操作回执](../evidence/observations/native-save-ui-observation.json)。额度输入框保持默认；真实提交值为 `max_input_tokens:172`、`max_output_tokens:32`。

两次均显示“校验失败，请检查模型配置”，未成功添加配置，现有模型及默认选择未修改。[当次截图裁剪](../evidence/screenshots/live-save-error-crop.png)保留完整表单与错误提示；原始截图因周围显示知识库内容而保留本地，原图哈希及纯像素裁剪坐标见 [attachments.json](../evidence/attachments.json)。

| 原始日志 | 模式 | 字节 / 事件 | 日志内首末事件时间（UTC） |
| --- | --- | --- | --- |
| 第一份 | Default / Strip private information | 1,475,588 / 7,370 | 01:37:28.429—01:47:45.433 |
| 第二份 | Everything / Include raw bytes | 6,298,844 / 19,547 | 02:08:14.470—02:34:07.698 |

第一份 SHA-256：`88f2927a9a4b4f35efbe924bc5a032a3d278d563fe0d30373d50cdefc0f875da`。

第二份 SHA-256：`d34d305b5abe297c657ed6401f9fab84b3f0c9ebfb36c4c500e9a5033427aa84`。

第二份采集窗口未控制到预期的短时范围，实际日志跨度约 **25 分 53 秒**，原件包含无关流量。日志已停止，原件放在本地权限 `0700` 的目录，文件权限 `0600`。最大文件大小设置为 8 MB。**完整日志、其他请求和账号头均未公开，也没有上传到第三方 NetLog Viewer。**

时间使用各原件的 `timeTickOffset + event.time` 换算，依赖设备时钟，不是独立授时证明。第二次实际保存请求时间为 **02:25:23.649 UTC / 10:25:23.649 新加坡时间**；相关遥测请求为 **02:25:25.129 UTC**。

## 请求 → 连接 → DATA 帧 → JSON

[第二份元数据摘录](../evidence/observations/native-netlog-raw-mode-metadata.json)按实际绑定关联：

`URL_REQUEST 8301 → HTTP_STREAM_JOB 8303 → HTTP2_SESSION 8311 → SOCKET 8310 / stream 1`

| 证据 | 原件零基事件索引 / 字节位置 |
| --- | --- |
| `POST https://ima.qq.com/cgi-bin/customize_models/add_model` | `10890`，设置扩展 initiator |
| session 显式绑定 socket | `10992` |
| 真实请求 DATA 帧，216 字节，payload 207 字节 | `SSL_SOCKET_BYTES_SENT` 事件 `11021`，解码后偏移 `0` |
| 真实响应 DATA 帧，70 字节，payload 61 字节 | `SSL_SOCKET_BYTES_RECEIVED` 事件 `11043`，解码后偏移 `363` |
| 响应的空 DATA / END_STREAM，9 字节 | 事件 `11080`，解码后偏移 `0` |

处理方式：base64 解码选定 socket 的 SSL 应用字节，按方向拼接，跳过存在的 HTTP/2 客户端 preface，读取 9 字节帧头，仅保留 type `0`（DATA）及目标 stream；按协议移除 padding 后拼接至 END_STREAM，再作 UTF-8 / JSON 解码。HTTP/2 格式依据 [RFC 9113 §4.1](https://www.rfc-editor.org/rfc/rfc9113.html#section-4.1)、[§6.1](https://www.rfc-editor.org/rfc/rfc9113.html#section-6.1)。

公开的 [live-wire-proof.json](../evidence/observations/live-wire-proof.json)包含上述 DATA 帧 base64、帧和 payload 的长度及哈希、原件事件索引及字节切片位置。任何读者可从这些公开帧重建[实际请求 JSON](../evidence/network/live-add-model-request.json)和[实际响应 JSON](../evidence/network/live-add-model-response.json)。没有公开 HPACK 头块或其他流的字节。

请求中假 Key 与 UI 输入相同，模型名为原始 `group/deepseek-v4-1-flash`；HTTP 状态为 `200`，响应内容为：

```json
{"code":100001,"msg":"校验失败，请检查模型配置"}
```

因此，这是收到 HTTP 响应后的业务校验失败，不是前端在输入 `/` 时直接阻止提交。**该通用错误仍不能唯一定位后端是拒绝 loopback、连接失败、模型名规则或其他原因。**

## 额外观察：失败请求参数进入遥测日志

同一原始日志中，另一个真实 POST 发往：

```text
https://galileotelemetry.tencent.com/collect
URL_REQUEST 8313 → JOB 8315 → SESSION 8194 → SOCKET 8193 / stream 11
```

[关联元数据](../evidence/observations/telemetry-netlog-metadata.json)固定到这一个 URL_REQUEST，不包括其他遥测请求。事件 `11164` 的 SSL_SOCKET_BYTES_SENT 中有一个 7,047 字节 DATA 帧，payload 为 7,038 字节的遥测 JSON。其 `/d2/2/message/0` 是一个嵌套 JSON 字符串：

- `url` 为上述 add_model 接口，`method` 为 POST，`status` 为 200，`ret` 为 `"100001"`，`isErr` 为 true。
- `param` 是完整请求参数字符串，**与实际 add_model 请求体逐字节相同**，包括同一个假 Key。
- `data` 解码后与实际错误响应 JSON 相同。

[telemetry-log-excerpt.json](../evidence/observations/telemetry-log-excerpt.json)仅公开这些字段及原件定位、完整私有 payload 的哈希。`param`、`data` 原字符串未改写；账号/设备信息、请求及响应头、trace/span、其他日志和顶层遥测字段全部省略，完整遥测 DATA 帧也不公开。

这证明**本次失败流程的测试 Key 没有在该日志参数中被遮蔽**，并实际进入另一条日志/遥测处理链路。它不说明所有版本和所有配置都会上报，也不证明真实密钥已泄露、服务器明文落盘或日志的保留/访问权限情况。两条请求均使用 HTTPS；这里看到的是 TLS 内部应用字节，不能称为公网明文传输。

## 可复核方法与边界

`npm test` 可在没有账号、私有日志或网络的情况下，从公开 DATA 帧重建 body、核验哈希及遥测参数匹配，再重跑原始函数的离线实验。

持有第二份本地原件时，可完整重跑筛选和解码：

```sh
python3 scripts/extract_live_capture.py /path/to/private/ima-netlog-raw.json \
  --request-source-id 8301 --telemetry-request-source-id 8313 \
  --check-dir .
```

导出到本地独立目录则把最后一项换成 `--output-dir _local/live-rebuilt`。脚本先核验 JSON 只含声明的测试字段，且 Key、URI、模型名和错误消息与 UI 回执相符；只导出已知无权限假 Key 实验的选定内容。

第一份仅有元数据的原件可单独复核：

```sh
python3 scripts/extract_netlog.py /path/to/private/ima-netlog.json \
  --check evidence/observations/native-netlog-metadata.json
```

NetLog 事件类型、phase、source 来自原件 constants；`event_index` 是原始 `events` 数组的零基索引。白名单只保留目标路径、状态、类型、长度、日期及绑定标识。

**原件未公开，因此第三方不能仅凭摘录独立证明其确实出自所承诺的原件；哈希也不是时间公证或设备认证。** 公开 DATA 帧能独立证明它们如何解码成公开 JSON，不能替代原件来源认证。NetLog 是客户端网络栈日志，不是网卡 PCAP；服务端内部校验、存储、日志保留及模型供应商调用仍未观测。

## 采集经过

2026-11-03 设置页的开发者工具被应用策略禁止；准备 NetLog 时遇到锁屏，未开始记录。2026-11-04 用户解锁后先取得去隐私日志。原始字节模式因会覆盖所有 ima 标签页并可能记录 Cookie/会话凭据，被自动审批拒绝；随后向用户说明具体范围并取得明确授权，才开启第二份 Everything 日志。两份日志都已确认 Log file written。

没有修改开发者工具策略、安装根证书、配置中间人代理、更改 TLS 校验或重启 ima。

工具依据：[Chromium NetLog 结构、时间与 SSL 应用字节说明](https://www.chromium.org/developers/design-documents/network-stack/netlog/)、[Chromium 官方采集与模式说明](https://new.chromium.org/for-testers/providing-network-details/)。
