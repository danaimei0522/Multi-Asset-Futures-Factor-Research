# 环境与依赖

实际验证：CPython 3.13.1，macOS，Python 标准库。Python >=3.11 是代码兼容目标；本次没有逐一测试 3.11/3.12 或其他系统，不宣称全矩阵通过。

运行/测试无需第三方包；requirements-runtime.txt 只有说明性注释，未伪造依赖锁文件。按 REPRODUCING.md 从源码运行不需要 pip install 或联网。

pyproject.toml 声明的 setuptools>=68 仅为构建依赖。requirements-build.txt 记录本机已安装的 setuptools==82.0.1；本机另有 pip 25.3、wheel 0.47.0，但它们不是策略运行依赖。该文件不是完整环境锁，也未宣称已经测试 pip 安装或 wheel/sdist 构建。公开源码包以白名单工具导出，不等于 PyPI 构建产物。

默认本金、合约规格、滑点等演示值不是平台配置。复现软件行为与复现市场业绩必须分开。
