# Nginx 上游重试放大与 502/504 排查

## 适用症状

网关层 502/504 同时升高；单个请求在多个 upstream 实例间重复出现；下游 QPS 高于入口 QPS；故障实例摘除后流量仍持续放大。

## 关键判断

Nginx 可以在与上游通信发生错误、超时或收到指定响应时，把请求交给下一个 upstream。若没有同时限制重试次数和总重试时间，一次入口请求可能转化成多次下游请求。对非幂等写请求重试还可能造成重复下单或重复扣款。

不要只调大 `proxy_read_timeout`。超时变大可能让连接和线程占用更久，使拥塞持续时间增加。先确认慢发生在连接建立、请求发送还是响应读取阶段，再对应检查 `proxy_connect_timeout`、`proxy_send_timeout` 和 `proxy_read_timeout`。

## 排查步骤

1. 用 request_id 关联网关和应用日志，统计单个入口请求对应多少次 upstream 尝试。
2. 比较入口 QPS、各 upstream 请求总量和 5xx；总量明显大于入口 QPS 时检查重试。
3. 检查 `proxy_next_upstream` 条件、`proxy_next_upstream_tries` 与 `proxy_next_upstream_timeout`。
4. 区分幂等 GET 与非幂等 POST；写请求没有业务幂等键时禁止透明重试。
5. 检查上游实例健康、连接池、线程池和下游依赖，确认重试放大前的第一处异常。
6. 修改配置后分批发布，观察入口错误率、upstream 请求放大倍数和业务重复率。

## 止损与预防

临时摘除已确认故障的 upstream；为重试设置次数和总时间上限；写请求使用幂等键；配置熔断与容量保护。保留变更前后指标，避免把“错误率下降但下游流量翻倍”误判为恢复。

## 参考

基于 Nginx 官方 `ngx_http_proxy_module` 中 proxy timeout 与 next upstream 指令整理：
https://nginx.org/en/docs/http/ngx_http_proxy_module.html

