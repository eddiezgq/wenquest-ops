# ADR-0024：作为模块部署到问渠国内服务器

- 状态：已接受（2026-10-29，项目负责人选定：WenQuest Ops；ERPNext 用第二个网址 qms-erp；同意按 24a–24c 做）
- 起因：项目负责人 2026-10-29：“问渠国内服务器的部署方式已经定了，质量 ERP 作为一个模块接进去”；约定见问渠仓库
  `docs/帮助/国内服务器加模块（质量ERP等）.md`（下称“约定”）。
- 相关：ADR-0023（中文版：`--china`、`--mirror`、国内演示企业）、ADR-0001（ERPNext 只用官方镜像）

## 背景

这里的“质量 ERP”指本仓库 WenQuest Ops（ERPNext + 质量体系中枢），在问渠国内服务器上给国内访客在线体验，用国内虚构演示
企业“海港五金供应（演示）”。服务器：阿里云上海 4 核 8 GB，问渠平台已占大半；连不上 GitHub 和 Docker Hub，东西都由
GitHub Actions 经 SSH 推过去；自带只监听本机的镜像仓库 `127.0.0.1:5000`；80/443 归问渠的 Caddy。

一整套 WenQuest Ops 有 12 个容器：ERPNext 7 个（后台、前端 nginx、websocket、两个队列、定时任务、一次性配置）、MariaDB、
两个 Redis、中枢、PostgreSQL，外加我们自己的 Caddy。ERPNext 不是轻量系统，约定的 2.5 GB 上限是本方案最大的风险。

## 决策（建议）

1. **镜像**：GitHub Actions 新增 `deploy-cn.yml`，在中枢镜像构建完后（`images.yml`）用 SSH 通道 + `skopeo copy` 把中枢镜像
   和 5 个基础镜像（ERPNext、MariaDB、Redis、PostgreSQL、Caddy）复制成 `127.0.0.1:5000/qms/<名字>:<标签>`。这正好是
   ADR-0023 `install.sh --mirror` 的命名（`--mirror 127.0.0.1:5000/qms`），不用另写一套。复制失败重试；不运行
   `garbage-collect`；中枢镜像只留最近 3 个版本。
2. **目录和项目名**：装在 `/opt/qms`，compose 项目名 `qms`（容器名不和问渠平台冲突）；`--china`（只用 DeepSeek、不显示
   Microsoft/Google 登录）。
3. **网址**：`install.sh` 新增 `--edge`：不再自己办证书、不占 80/443；我们的 Caddy 改名 `qms-demo-edge`，只在容器内
   监听 80，接到外部网络 `qms-edge`，按访问的域名分给中枢和 ERPNext。**ERPNext 需要自己的网址**（中枢的“打开 ERPNext”
   和单点登录要用），建议问渠那边的 `qms.caddy` 同时转两个名字：`qms.<主域名>`（WenQuest Ops）和
   `qms-erp.<主域名>`（ERPNext），都转给 `qms-demo-edge:80`。
4. **内存**：新增 `deploy/docker-compose.small.yml`（`--small` 使用），每个容器设 `mem_limit`，合计上限约 2.4 GB：

   | 容器 | 上限 | 怎么省 |
   | --- | --- | --- |
   | ERPNext 后台 | 600 MB | gunicorn 2 个进程 |
   | ERPNext 队列（合成 1 个） | 320 MB | 短队列、长队列由一个 worker 处理 |
   | ERPNext 定时任务 | 160 MB | |
   | ERPNext websocket / 前端 nginx | 96 / 48 MB | |
   | MariaDB | 448 MB | 缓冲池 192 MB |
   | Redis ×2 | 48 / 48 MB | 限内存 32 MB |
   | 中枢 | 400 MB | 1 个 uvicorn 进程 |
   | PostgreSQL | 192 MB | shared_buffers 64 MB |
   | 边缘 Caddy | 48 MB | |

   第一次装时 `bench new-site` 和设置向导要的内存多，这两步用一次性容器临时放宽到 1.5 GB，装完即退。CI 的 `install-cn`
   改用同样的上限和 `--edge`，所以每次 CI 都在验证“2.4 GB 装得下、跑得动、演示数据导得进”。实际占用以服务器上为准，
   不够时按约定升级服务器。
5. **部署**：推送到 main 后自动部署（与问渠平台相同），也可手动运行；在服务器上先拿锁
   `flock -w 1500 /tmp/wenquest-deploy.lock`，第一次 `install.sh`、以后 `upgrade.sh`。第一次装时导入国内演示企业。
6. **密钥**：SSH 钥匙用模块专用一把（Secrets `CN_DEPLOY_HOST`、`CN_DEPLOY_SSH_KEY`，由项目负责人在服务器上生成）。
   DeepSeek 钥匙由项目负责人自己写进 `/opt/qms/.env`（`WQO_DEEPSEEK_API_KEY`），不经过聊天；没填时助手用规则引擎回答。
   老板账号的密码同样由项目负责人在服务器上设一次（给出命令），不放进仓库和 Actions 日志。
7. **备份**：每天 04:10 用 `backup.sh` 在服务器上备份（错开问渠 03:30），留最近 7 份，放 `/opt/qms/backups`，不传出境。
8. **备案期间**：可以部署、在服务器内部测（SSH 通道打开看），不对外。

## 分步与验收

| 步 | 内容 | 验收 |
| --- | --- | --- |
| 24a | `--edge`、`--small`、项目名、一次性放宽内存的装法；CI `install-cn` 改用它们 | CI 在 2.4 GB 上限下装好、导入国内演示企业、帮助演示走通 |
| 24b | `deploy-cn.yml`：复制镜像、传文件、拿锁、安装或升级、每日备份、清理旧版本 | 项目负责人填好 Secrets 后第一次部署成功；服务器上 `status.sh` 全部正常 |
| 24c | 告诉问渠主仓库加 `qms.caddy`（两个名字）；备案下来后对外 | `https://qms.<主域名>` 能登录 |

## 后果

- 本仓库多一种部署方式（在别人的服务器上当模块），美国和独立部署的默认行为不变。
- 内存上限下 ERPNext 只能少量并发，适合演示和小企业试用，不适合真实生产负载。

## 施工记录

- **24a（2026-10-29）**：`install.sh --edge`（`docker-compose.edge.yml`、`Caddyfile.edge`）、`--small`
  （`docker-compose.small.yml`）、`--project`，选过的写进 `.env`，`lib.sh` 按它拼 compose 命令；`status.sh` 在 `--edge`
  下经边缘 Caddy 按域名检查。CI `install-cn` 改成与服务器完全相同的装法（项目 qms、`--china --edge --small`，前面放一个
  替身 Caddy 占 443），导入国内演示企业、走完中文帮助演示。**实测内存**（导入演示数据后）：ERPNext 后台 318 MB、MariaDB
  275 MB、中枢 80 MB、队列 52 MB、定时任务 51 MB、PostgreSQL 40 MB、其余各十几 MB 以下，合计约 0.87 GB，远低于 2.4 GB 上限；
  没有容器因内存被杀。
- **24b（2026-10-29）**：`.github/workflows/deploy-cn.yml`：中枢镜像构建完（或手动运行）后，SSH 通道 + skopeo 把中枢和 5 个
  基础镜像复制成 `127.0.0.1:5000/qms/...`（失败重试，不做 garbage-collect，中枢只留最近 3 个版本）；文件传到 `/opt/qms`；
  拿问渠的部署锁后第一次 `install.sh`（国内演示企业、`--china --edge --small --project qms --mirror 127.0.0.1:5000/qms`）
  并导入演示数据，以后 `upgrade.sh`；每天 04:10 备份留 7 份（deploy 用户的 crontab）；最后报告状态和内存。网址取服务器上
  问渠平台 `.env` 的 `SITE_DOMAIN`：`qms.<主域名>` 和 `qms-erp.<主域名>`，也可用仓库变量 `CN_QMS_DOMAIN` 指定。
  另加两个服务器上用的小脚本：`owner-password.sh`（设老板密码）、`ai-key.sh`（填 DeepSeek 钥匙并重启中枢，先拿部署锁），
  都在终端里问、不回显、不进命令历史。没有 Secrets `CN_DEPLOY_HOST`、`CN_DEPLOY_SSH_KEY` 时部署流程什么也不做。
