# Kubernetes CrashLoopBackOff 诊断 Runbook

## 先理解状态

CrashLoopBackOff 不是根因，而是 kubelet 在容器反复启动失败后执行指数退避时显示的状态。Pod phase、container state、last state、reason 和 exit code 才是定位入口。不断删除 Pod 可能清掉现场，但不会修复错误配置或应用崩溃。

## 排查步骤

1. `kubectl describe pod` 查看 Events、镜像、探针、挂载和调度信息。
2. 查看当前容器日志，并用 `kubectl logs --previous` 获取上一次已退出容器日志。
3. 检查 last state：`OOMKilled` 优先看 limit、工作集和内存增长；非零 exit code 结合应用栈分析。
4. 对照最近 Deployment、ConfigMap、Secret、镜像和依赖变更。
5. 区分 liveness、readiness、startup probe：readiness 失败会摘流量，liveness 失败会触发重启；慢启动应用应使用 startup probe 保护启动阶段。
6. 检查外部依赖、DNS、权限、只读文件系统和 Volume 挂载。
7. 若镜像缺少调试工具，使用临时调试容器；生产操作需遵循 RBAC 和审计要求。

## 修复与验证

按根因修复，而不是只提高 restartPolicy 或资源上限。发布后观察 restartCount 是否停止增长、Ready 是否稳定、错误率和启动耗时是否恢复；保留旧 Pod 日志、Events 和发布版本作为回归证据。

## 参考

基于 Kubernetes 官方 Pod lifecycle、Debug Pods 与 probe 文档整理：
https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/

