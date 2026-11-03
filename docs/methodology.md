# 方法与证明边界

## 断网复现如何工作

复现依次使用原始 bundler helpers、host resolver、snake_case helper、JSON 字段转换器、Ky HTTP 客户端、KyService、FetchService、自定义模型 HTTP 服务、保存 Presenter 和输入 hook。它们均由 manifest 定位并以片段哈希校验。

使用的 Key 固定为 `IMA_EVIDENCE_DUMMY_KEY_DO_NOT_USE`，是无权限、可公开的测试字符串。表单中的 `api_uri` 则保留问题场景的 localhost 地址。生成 Request 的 URL 指向 ima 服务，localhost 地址只出现在其 JSON 字段内。

替换的依赖：

| 依赖 | 替身 | 影响 |
| --- | --- | --- |
| 浏览器环境 | 合成的 ima User-Agent、扩展 origin、空宿主 host 覆盖 | 只演示生产默认 host；不证明真实运行时宿主覆盖值 |
| host resolver 的查询参数 helper | `URL.searchParams.has()` | 本次合成 URL 无相应参数；原始 resolver 仍实际执行 |
| 账号请求头 | 空对象 | 不读取、不使用真实 cookie 或票据 |
| 可选应用层加密服务 | 未注入 | 捕获应用层构造结果；不据此证明真实请求未加密 |
| 错误类、枚举、store、reporting | 本地依赖桩 | 不验证登录刷新、错误码定义、统计上报或持久化 |
| `globalThis.fetch` | 读取原始 Request，返回合成 JSON 错误 | 无真实网络；合成返回结果不代表腾讯真实响应 |
| 输入 hook 的 React callback/toast 依赖 | 同步 callback 和本地记录器 | 验证输入转换，不验证完整 UI 事件系统 |

没有对生产应用打补丁、修改其二进制、安装证书、改变系统代理或关闭 TLS 校验。

## 8 项检查

1. 恰好构造一条保存请求。
2. 生产默认目标为 ima `customize_models/add_model`。
3. 方法为 POST。
4. JSON `model_info.api_key` 保留假 Key。
5. 配置的 localhost URI 出现在 `model_info.api_uri`。
6. 原始保存逻辑将合成错误传回调用方。
7. 三种名称输入原样保留，其中包含一级和多级 `/`。
8. 输入 hook 没有产生限制提示。

## 不能从这些证据推出的结论

- 没有证明腾讯已收到本次用户历史保存操作中的特定 Key；当前公开材料没有对应真实报文。
- 没有证明所有版本、全部功能、所有账号或所有地区行为相同。
- 没有证明服务器明文落盘、日志记录 Key、保留期限、内部访问权限或删除后的备份处理。
- 没有证明已发生密钥泄露、盗用、未经授权访问或安全漏洞。
- 不能排除 ima 服务端对模型名称另有规则。
- 不能从“前端未补接口路径”推出“服务器必定不规范化地址”。
- 不能把 localhost 解释写成已观察的唯一根因：主动拒绝私有地址、连接失败、协议限制及其他校验分支尚未区分。

## 安全含义

将 Key 交给服务端处理会增加需要信任的主体。该架构可以是正常的云端代调用设计；风险判断取决于用户预期、明确披露、Key 的权限和服务端保护。客户端 JSON 中存在字符串不等同于线上没有 TLS，也不等同于服务端明文存储。
