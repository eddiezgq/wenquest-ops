# 第 1 期验收：项目负责人清单

第 1 期第 10 项（`docs/plan.md`）。CI 每次完整安装都会自动跑一遍：干净机器安装 → 载入演示企业 → 中枢与 ERPNext
逐张核对 → 截图录像 → 浏览器冒烟测试（7 个角色逐页打开；采购单、延误说明、来料检验、不合格品审批关闭四条流程）。
下面是给项目负责人自己装一遍、亲手看一遍用的。约需 1 小时（其中安装等待 20–30 分钟）。

## 一、准备一台机器

- **Ubuntu 22.04 或 24.04**，4 核、8 GB 内存（建议 16 GB）、40 GB 空闲磁盘。只在 Ubuntu 上测过（CI）。
  - Windows 电脑：在 WSL2 的 Ubuntu 里装，见下面“Windows 用 WSL2”。PowerShell 里不能直接运行这些命令
    （`&&`、`变量=值 命令`、`\` 续行、`.sh` 脚本都是 Linux shell 的写法）。
  - Mac：暂不支持（安装脚本按 Linux 写）。
  - 也可以租一台云主机（Ubuntu、8 GB 内存）；用完删掉。
- 装 Docker：`curl -fsSL https://get.docker.com | sh`，然后 `sudo usermod -aG docker $USER` 并重新登录。
- 装 git，拉代码：`git clone https://github.com/eddiezgq/wenquest-ops.git && cd wenquest-ops`

### Windows 用 WSL2

1. **装 Ubuntu**：以管理员身份打开 PowerShell，运行 `wsl --install -d Ubuntu-24.04`，按提示重启，
   再从开始菜单打开 “Ubuntu 24.04”，设一个 Linux 用户名和密码。以后的命令都在这个 Ubuntu 窗口里输入。
2. **给够内存**：WSL 默认只用电脑一半的内存。在 PowerShell 运行 `notepad $env:USERPROFILE\.wslconfig`，写入
   下面两行（电脑 16 GB 写 `10GB`，32 GB 写 `16GB`），保存后运行 `wsl --shutdown`，再打开 Ubuntu：
   ```
   [wsl2]
   memory=10GB
   ```
   在 Ubuntu 里 `free -g` 看 total 至少 8。
3. **Docker**（2026-10-13 项目负责人实测走通的是第一种）：
   - **已装 Docker Desktop**：打开它，Settings → Resources → **WSL integration** 打开 Ubuntu-24.04，Apply & restart。
     不要再在 Ubuntu 里装 Docker（两份会冲突）。
   - **没装 Docker Desktop**：在 Ubuntu 里 `curl -fsSL https://get.docker.com | sh`、`sudo usermod -aG docker $USER`，
     `exit` 后重新打开；连不上时 `sudo service docker start`。

   在 PowerShell 里 `wsl -l -v` 若默认（带 `*`）是 docker-desktop，运行 `wsl --set-default Ubuntu-24.04`：
   docker-desktop 是 Docker 自己用的，不能在里面装。进入 Ubuntu 后提示符是 `用户名@电脑名:~$`。
   `docker run --rm hello-world` 打印欢迎信息即可。
4. **代码放在 Ubuntu 的主目录里**，不要在 `/mnt/c/...` 下运行（慢，且 Windows 换行符会弄坏脚本）。
   仓库是私有的，Ubuntu 里 `git pull` 会要 GitHub 账号；最省事的是复制 Windows 里已经拉好的代码，再按仓库原样重写一遍文件：
   ```bash
   cp -r /mnt/c/Users/<你的 Windows 用户名>/wenquest-ops ~/
   cd ~/wenquest-ops && git config core.autocrlf false && git reset --hard
   ```
5. 接着做下面第二步。装好后在 **Windows 的浏览器**里打开 `https://ops.localtest.me` 即可（WSL2 把端口转到了 Windows）。

## 二、安装（与 CI 相同的做法）

在本机试用不需要域名：`ops.localtest.me` 这个公共域名永远指向本机 127.0.0.1。

```bash
docker build -t wenquest-ops-hub:local .                       # 中枢镜像在本机构建，不用镜像仓库令牌
mkdir -p ~/wqo && cp -r deploy/. ~/wqo/
WQO_HUB_IMAGE=wenquest-ops-hub:local ~/wqo/install.sh \
  --company companies/demo-harbor-lane.yaml --domain ops.localtest.me --tls-internal --no-pull
```

安装时会问 Dana Owner 的口令，自己定一个记下来。装完再载入演示业务（只能载一次，几分钟）：

```bash
cd ~/wqo && docker compose -p wqo --env-file .env -f docker-compose.yml exec -T hub python -m wqops.demo.load
```

云主机上没有浏览器时：在自己电脑上 `sudo ssh -L 443:127.0.0.1:443 用户@主机`（占用本机 443 端口，要管理员权限），再用本机浏览器打开下面的地址。

## 三、逐项验收

浏览器打开 `https://ops.localtest.me`（证书是内部签发的，浏览器提示不安全时点 Advanced → Proceed；ERPNext 的地址 `erp.ops.localtest.me` 第一次也会提示一次）。用 `dana@demo.example` 登录。
每项打勾或写下问题。

| # | 看什么 | 应当看到 | 结果 |
| --- | --- | --- | --- |
| 1 | 第一次登录 | 分步引导自动出现，7 步走完；Help 里能重开 | |
| 2 | 仪表盘 | 6 个数；鼠标停在数上说明怎么算的；下方有 Needs attention 列表 | |
| 3 | 供应商按时率 | Gulf Fasteners (Demo) 最低（常晚到的那家） | |
| 4 | 逾期订单追因 | Anomalies 里一张逾期订单 → 等 HX-BOLT-M8 → 采购单晚到 → Gulf Fasteners | |
| 5 | 助手 | 问 “Which orders are late, and why?”，回答里的单号能点开；页面写明没设模型密钥时用内置规则 | |
| 6 | 起草与确认 | 在物料 HX-BOLT-M8 页起草补货采购单 → Drafts 确认 → ERPNext 里出现草稿采购单 | |
| 7 | 质量 · 不合格品 | NCR-00001（HX-BOLT-M8 来料不合格，已处置），关联 CAPA-00001 | |
| 8 | 质量 · CAPA | CAPA-00001 有一项逾期措施，异常列表里也有它 | |
| 9 | 质量 · 来料检验 | CBL-12-50 的收货单草稿在等检验；能起草检验单 | |
| 10 | 质量 · SPC | HX-BOLT-M8 螺纹中径控制图：一批超上限（被拒那批），末段逐步上漂并被判异 | |
| 11 | 质量 · 签字 | 新开一张不合格品，选 “Use as is” → 自己不能批，要另一人（如 Sam）用口令批；关闭要口令 | |
| 12 | 人员与角色 | 菜单 People 里给 Alex（销售）设口令；退出，用 Alex 登录：菜单里没有 Quality 和 People；点右上角名字进 My account 改自己的口令 | |
| 13 | 进 ERPNext | 菜单 “ERPNext ↗” 直接进入，不用再登录 | |
| 14 | 帮助 | Help 8 页英文，质量、仪表盘等页有截图 | |
| 15 | 运维 | `~/wqo/status.sh` 全绿；`~/wqo/backup.sh` 出备份文件；按 `docs/ops/README.md` 恢复一次 | |

## 四、问题怎么记

每个问题开一个 issue（标题写现象，正文写第几项、做了什么、看到什么、截图）。
装不上的问题也算验收结果：说明运维文档或安装脚本要改。

第 1 期通过的条件（`docs/plan.md`）：CI 通过，且项目负责人在自己电脑上装好并走完上表。
