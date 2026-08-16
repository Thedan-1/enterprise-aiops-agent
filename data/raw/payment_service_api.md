# payment-service 服务文档

## 概述

payment-service 负责支付预授权、扣款、退款。技术栈：Go，数据库为 PostgreSQL。对接外部第三方支付网关。

## 关键接口

### POST /api/payments/pre-authorize
支付预授权，被 order-service 在创建订单流程中同步调用。

## SLA

正常情况下 P95 延迟应小于 300ms。如果第三方支付网关变慢，payment-service 自身的P95延迟会相应上升，进而影响所有同步调用它的上游服务（如 order-service）。

## 已知风险点

payment-service 对第三方支付网关的调用配置了 2 秒超时和 3 次重试（无退避，back-to-back重试），在第三方网关本身就不稳定的情况下，重试会放大对第三方的压力，也会拉长payment-service自身的响应时间。这是一个已知的待优化项：应该改为指数退避重试，并配合熔断器。
