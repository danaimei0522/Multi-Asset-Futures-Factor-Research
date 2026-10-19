# 可复现运行

Python >=3.11，标准库实现，无运行时第三方依赖、无需联网或安装平台 SDK。实际测试版本和结果见 TEST_RESULTS.md。

在项目根目录运行：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 scripts/make_synthetic.py
python3 scripts/run_backtest.py --bars outputs/synthetic/bars.csv --routes outputs/synthetic/routes.csv --calendar outputs/synthetic/calendar.csv --config outputs/synthetic/config.json --output outputs/synthetic/result.json
```

合成数据使用虚构价格、合约规格及每日连续人工日历，含周末；不代表真实交易日历或市场收益。默认本金同样仅用于软件演示。

真实数据运行时替换行情、路由、日历、配置四个输入路径，在 config 中显式配置 strategy.initial_cash、start、end 和全部合约规格。输出包含独立模拟标签、配置、四个输入文件 SHA256、引擎 SHA256、Python 版本、权益、成交、事件和期末仓位。比较运行时同时保存项目版本和全部源文件；当前哈希只覆盖 engine.py，不是完整源代码存档。

指标不含“平台复现已通过”结论。导出的成交数量不等于往返次数。期末未强平。模拟报错不得挑选部分输出当作有效回测。当前没有真实市场独立业绩文件。

审计修复后 API 要求显式日历，例如：

```python
engine.run(bars, routes, start=start, end=end, calendar=verified_sessions)
```

原先只提供 bars/routes 的调用现在会拒绝执行。这是数据完整性接口变更，策略参数未变。直接传 routes 字典仍由调用者负责证明时点有效性，CSV 的 known_on 校验不能替代数据来源审计。


## 公开源码包的完整性核对

Python 实测范围与可选构建依赖见 ENVIRONMENT.md。整个发布内容的指纹由 release_manifest.json 记录，独立于回测结果中的 engine_sha256。

```bash
python3 -B scripts/release.py --verify
python3 -B scripts/release.py --export dist/research-framework-source.zip
```

导出只读取 release_allowlist.txt，拒绝符号链接、缺失/越界文件、哈希不匹配及已知敏感内容模式；不会把当前目录整体打包。首次校验及导出无需更新清单。只有经过人工审查的文件有意变更后才运行 `python3 -B scripts/release.py --refresh-manifest`，然后重新验证与测试；刷新哈希不是安全审查的替代。

公开包不包含 outputs/，因此新用户须先运行 make_synthetic.py，再运行回测命令。用户自己的真实数据和路径不得加入发布清单。发布扫描为启发式规则，不构成无秘密或第三方权利的完整证明。当前许可状态为保留权利，不是开放源代码复用授权。
