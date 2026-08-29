# Kubernetes Pod Pending 排查

Pod 长时间 Pending 通常不是应用代码问题。查看 scheduler events，常见原因包括 CPU/Memory 不足、nodeSelector 或 affinity 无可匹配节点、PVC 未绑定、污点未配置 toleration，以及镜像拉取凭证错误。

先读 Events，再检查 requests 与节点 allocatable。若是 PVC，检查 StorageClass 和 provisioner；若是调度约束，验证标签和亲和性规则。不要直接删除 Pod 反复重建，这不会改变不可满足的调度条件。

