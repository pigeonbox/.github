# PigeonBox `.github`

组织级公共仓库：存放组织主页等组织级配置。

组织主页（在 [组织页](https://github.com/orgs/pigeonbox) 顶部展示的 README）位于 [`profile/README.md`](profile/README.md)——GitHub 只认这个路径，根目录 README 不会显示在组织页上。

如需更新组织主页，请直接编辑 [`profile/README.md`](profile/README.md)。

## 组织级资产

- **质量看板**：<https://github.com/orgs/pigeonbox/projects/1> —— 六分类（Security / Correctness / Reliability / Platform / Product / Community）× 三态（已验证缺陷 / 待确认问题 / 未来功能提案），跨仓阻塞关系 / 按列车归档 / 真机覆盖率的统一视图。维护约定见 [`docs/PROJECT-BOARD.md`](docs/PROJECT-BOARD.md)，同步脚本 [`scripts/sync-board.py`](scripts/sync-board.py)。
