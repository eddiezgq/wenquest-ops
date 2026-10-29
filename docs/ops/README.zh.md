# WenQuest Ops 安装与运维手册（国内版）

本手册写给为企业安装和运行 WenQuest Ops 的 IT 人员或运维服务商，适用于服务器在中国大陆的企业。
英文版见 [README.md](README.md)；国内版与英文版功能相同，只在语言、格式、AI 提供方、登录方式和镜像来源上不同（ADR-0023）。

全部服务跑在一台装了 Docker 的 Linux 服务器上。WenQuest Ops 只通过 REST API 与 ERPNext 通信；
ERPNext 使用官方镜像，不做任何修改。

## 安装哪些服务

| 服务 | 作用 | 外部能否访问 |
| --- | --- | --- |
| caddy | 两个网址的 HTTPS 入口，自动申请证书 | 能，80 和 443 端口 |
| hub | WenQuest Ops（网页和 API） | 经 Caddy |
| db | WenQuest Ops 的 PostgreSQL | 否 |
| erp-* | ERPNext v16：网页、后台任务、定时任务、websocket | ERPNext 网页经 Caddy |
| erp-db、erp-redis-* | ERPNext 的 MariaDB 和 Redis | 否 |

## 准备工作

- Ubuntu 22.04 或 24.04（其他装了 Docker 的 Linux 也可以），4 核 CPU，8 GB 内存（建议 16 GB），
  40 GB 可用磁盘（建议 100 GB），另加文件库的空间：大约等于企业文件夹的大小，保留备份时再翻一倍（见下文“文件库”）
- Docker Engine 和 compose 插件。`curl -fsSL https://get.docker.com | sh` 在国内不一定能连上；连不上时请按云服务商或
  国内软件源的说明安装。装好后 `docker compose version` 应能显示版本号
- 两个指向这台服务器的域名，例如 `ops.example.cn` 和 `erp.ops.example.cn`，并开放 80 和 443 端口
  （云服务器还要在控制台的安全组里放行）；内网使用可以用 `--tls-internal`，见下文
- 企业清单 `company.yaml`（见第 1 步）
- 国内镜像仓库的地址和拉取令牌：由提供 WenQuest Ops 的一方给您（例如 `registry.example.cn/wenquest`，
  这里只是示例，请以对方给的为准）

### 域名备案与证书

- **服务器在中国大陆时，域名要先完成 ICP 备案，网站才能在 80/443 端口对外提供访问。** 未备案的域名，
  请求通常会被云服务商拦下，Let's Encrypt 也就无法签发证书。备案请找您的云服务商办理。
- 备案完成、两个域名都解析到这台服务器后，Caddy 会自动向 Let's Encrypt 申请证书并续期，安装时用 `--email` 填联系邮箱。
- 只在企业内网使用时，加 `--tls-internal`：Caddy 用自己签发的证书，不需要公网域名和备案，但两个名字仍要能在内网解析
  到这台服务器（内网 DNS 或各电脑的 hosts 文件）。浏览器会提示证书不受信任，属正常现象。

### 镜像

国内连不上或连不稳 Docker Hub 和 ghcr.io。项目会把 WenQuest Ops 的镜像和它用到的全部基础镜像（ERPNext、Caddy、
PostgreSQL、MariaDB、Redis）复制到一个国内镜像仓库。安装时用 `--mirror <仓库地址>` 从那里拉取全部镜像，
用 `--registry-token <令牌>` 登录。登录用户名默认是 `wqo`；如果对方给了别的用户名，安装前设置 `WQO_REGISTRY_USER`。

## 1. 填写企业清单

企业清单描述企业本身、场地、仓库、部门、人员和启用的模块。国内企业建议直接从国内演示企业的清单
`demo-haigang.yaml`（虚构的“海港五金供应（演示）”）改起，它已经按国内设置好。先登录镜像仓库，再从镜像里取出这份清单：

```bash
echo '<拉取令牌>' | docker login registry.example.cn -u wqo --password-stdin
IMG=registry.example.cn/wenquest/wenquest-ops-hub:latest
docker run --rm "$IMG" cat /app/companies/demo-haigang.yaml > company.yaml
```

用文本编辑器（UTF-8 编码）打开 `company.yaml`，把每一项都换成本企业的真实信息。公司部分的国内设置：

```yaml
demo: false                    # 真实企业填 false；true 只用于虚构的演示数据
company:
  name: 您的公司名称            # 在 ERPNext 里建立的公司，可以用中文
  abbr: ABC                    # 字母和数字，最多 6 位，作仓库名的后缀（演示用的是拼音首字母 HGWJ）
  country: China
  currency: CNY
  timezone: Asia/Shanghai
  fiscal_year_start: "01-01"
  date_format: yyyy-mm-dd
  language: zh                 # 界面、中枢的文字和生成的文书用中文；ERPNext 也装成中文
  units:
    weight: kg
    length: cm
```

场地、仓库、部门、人员的 `id` 只能用小写英文字母、数字和 `-`；名称可以用中文。人员的邮箱用来登录，必须每人一个。
角色可选 `owner`、`ops_manager`、`warehouse`、`purchasing`、`sales`、`quality`、`ai_specialist`，至少要有一位 `owner`。

改完后检查：

```bash
docker run --rm -v "$PWD":/w -w /w "$IMG" python -m wqops.company check company.yaml
```

出错时会写明是哪个字段、哪一行。

也可以用 Excel 模板填写（`python -m wqops.company template company.xlsx`，再 `import`，用法同英文版）。
模板里预填的是英文的美国演示企业：请在“语言”一行填 `zh`，并把国家、币种、时区、日期格式和单位改成上面的国内值。在服务器上用镜像运行时加 `-u "$(id -u):$(id -g)"`，
否则写不进当前目录：

```bash
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/w -w /w "$IMG" python -m wqops.company template company.xlsx
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/w -w /w "$IMG" python -m wqops.company import company.xlsx company.yaml
```

### ERPNext 的中文设置与会计科目表

`language: zh` 时，安装脚本让 ERPNext 的设置向导用中文：系统语言中文、国家中国、人民币、北京时间。
会计科目表用 ERPNext 的**标准科目表**，科目名为中文。ERPNext v16 自带的中国科目表在它的“未核实”目录里，设置向导不提供，
所以没有用。如果财务需要按国内会计制度设科目，请由会计在 ERPNext 里调整科目表。

ERPNext 的系统语言、公司名称、币种和时区在安装时定下，之后改企业清单不会改这些。

## 2. 安装

把 `deploy/` 目录复制到服务器（例如 `/opt/wenquest-ops`），把 `company.yaml` 也放进去，然后运行：

```bash
cd /opt/wenquest-ops
./install.sh --company company.yaml --domain ops.example.cn --email it@example.cn \
             --china --mirror registry.example.cn/wenquest --registry-token <拉取令牌>
```

内网使用时把 `--email it@example.cn` 换成 `--tls-internal`。ERPNext 的网址默认是 `erp.` 加主域名，需要别的名字时用
`--erp-domain`。

- `--china`：标记为国内部署（`.env` 里写入 `WQO_DEPLOYMENT=cn`）：AI 只用 DeepSeek，不提供 Microsoft / Google 登录。
- `--mirror`：所有镜像都从这个仓库拉，不再访问 Docker Hub 和 ghcr.io。
- `--image <标签>`：指定 WenQuest Ops 镜像的版本，默认 `latest`。

第一次运行需要 15–25 分钟（拉镜像、建 ERPNext 站点、跑设置向导）。脚本依次：

1. 检查内存、磁盘和 Docker；
2. 写 `.env`，其中的密码和密钥自动生成（权限 600；请保管好它和备份）；
3. 检查企业清单，存为 `company/company.yaml`；
4. 建 ERPNext 站点，按企业清单用中文跑设置向导（公司、国家、币种、时区、会计年度）；
5. 为 WenQuest Ops 生成 ERPNext 的 API 密钥，再在 ERPNext 里建仓库、部门和地址；
6. 启动 WenQuest Ops 和 Caddy，做第一次备份，显示运行状态。

`install.sh` 可以重复运行，已完成的步骤会跳过。第一次给的 `--china` 和 `--mirror` 记在 `.env` 里，重复运行时
不必再写；要换 WenQuest Ops 的版本用 `--image` 或 `upgrade.sh`。

ERPNext 管理员账号是 `Administrator`，密码是 `.env` 里的 `ERP_ADMIN_PASSWORD`。

### 登录

企业清单里的人员就是能登录的人，角色也取自清单。从清单里删掉的人员，在下次升级
（`./upgrade.sh --company company.yaml`）或 hub 重启时停用。

国内版只用 WenQuest Ops 自己的账号和密码登录。**Microsoft 365 和 Google 登录在国内版中不提供**（国内无法稳定访问），
即使 `.env` 里填了相关配置也不会显示；企业微信、钉钉登录以后再定。

- 清单里第一位 owner 的密码在安装时设置：运行 `install.sh` 前设置环境变量 `WQO_OWNER_PASSWORD`，或在提示时输入
  （至少 10 位，含字母和数字）。
- 其他人的密码由 owner 在工作区的“人员”页面设置（或在服务器上设置，见下）；每个人可以在“我的账户”（点自己的名字）里改。
- 在服务器上设置：`echo '密码' | docker compose -p wqo exec -T hub python -m wqops.hub.accounts set-password 邮箱`
- 连续输错 5 次密码，账户锁定 10 分钟。登录事件都有记录。

### 打开 ERPNext

人员从 WenQuest Ops 打开 ERPNext，在 ERPNext 登录页选择 **Login with WenQuest Ops**（使用 WenQuest Ops 登录），
不需要再输一次密码。每次登录时，按此人在 WenQuest Ops 的角色建立或更新 ERPNext 账号和标准角色（例如仓库角色对应
Stock User，质量角色对应 Quality Manager 和 Stock User）。在 WenQuest Ops 里停用的人员不能再这样进入。
Administrator 账号保留自己的密码。

### 界面语言

界面默认使用企业清单的语言（`language: zh` 时为中文，金额按人民币、日期按 YYYY-MM-DD 显示）。每个人可以在侧栏菜单里
切换“中文 / English”，选择记在自己的浏览器里。中枢生成的文书（程序文件、导出表格等）和写给 ERPNext 的文字按企业语言。

## 3. 日常运维

以下命令都在安装目录（例如 `/opt/wenquest-ops`）里运行。

| 任务 | 命令 |
| --- | --- |
| 查看状态（有问题时退出码为 1） | `./status.sh` |
| 立即备份 | `./backup.sh` |
| 恢复 | `./restore.sh backups/wqo-<时间>.tar.gz` |
| 升级 | `./upgrade.sh [标签] [--company company.yaml]` |
| 查看日志 | `docker compose -p wqo logs -f hub` |
| 立即同步 ERPNext 的变化 | `docker compose -p wqo exec hub python -m wqops.hub.sync run` |
| 同步状态 | `docker compose -p wqo exec hub python -m wqops.hub.sync status` |
| 导入虚构演示业务（只限演示清单，只做一次；国内演示清单导入中文的一套） | `docker compose -p wqo exec hub python -m wqops.demo.load` |
| 给早先导入的演示补上质量样例记录（只限演示清单；已有记录的物料跳过） | `docker compose -p wqo exec hub python -m wqops.demo.quality` |
| 从事件记录重建运营中枢的对象 | `docker compose -p wqo exec hub python -m wqops.hub.ont.project --rebuild` |

### 备份

`backup.sh` 生成 `backups/wqo-<时间>.tar.gz`，包含 WenQuest Ops 数据库、文件库的文件、ERPNext 的数据库和文件、
`.env` 和企业清单，保留最新的 14 份（`WQO_KEEP`）。设成每天自动备份：

```bash
echo "30 2 * * * root /opt/wenquest-ops/backup.sh" > /etc/cron.d/wenquest-ops-backup
```

设置 `WQO_BACKUP_COPY_TO=/mnt/offsite` 可把每份备份再复制到另一个位置（另一块磁盘、挂载的存储桶）。
备份里有密码，请按保管密码的要求保管备份。

### 恢复

`restore.sh backups/wqo-<时间>.tar.gz` 先要求确认（或加 `--yes`），然后恢复两个数据库、文件库的文件和 ERPNext 的文件。
备份里的配置解压到 `backups/restore-<时间>/` 供对照，不会覆盖当前的 `.env`。

### 升级

`upgrade.sh` 先备份，再拉新镜像并重启。它沿用安装时的镜像仓库，国内安装会继续从国内仓库拉。标签可用 `latest`、
版本号或 `sha-<7 位提交号>`，以国内仓库里实际有的为准。带 `--company` 时先检查新清单（有错误就什么都不改），
再建新增的仓库、部门和地址。公司名称、币种和时区在安装时定下，不能通过升级改。

### ERPNext 同步

WenQuest Ops 每 5 分钟读一次 ERPNext（`.env` 里的 `WQO_SYNC_SECONDS`；设为 `0` 关闭）：物料、仓库、客户、供应商、
库存台账、销售订单、发货单、采购订单、采购收货、质量检验，以及删除。每次变化存为一条事件，只取上次以来的变化；
中断的同步下次从断点继续。安装后第一次同步，ERPNext 数据多时可能要几分钟。有“修改平台设置”权限的人可以立即发起同步
（`POST /api/sync/run`）；`GET /api/sync/status` 显示已读取的内容和最近一次运行，失败时包括错误。
每次同步后，运营中枢把新事件变成对象和关联（物料、订单、收货、库存等）；定义它们的本体在 `wqops/ontology/`。

### AI 助手

助手只用中枢自己的工具回答订单、库存、供应商和质量方面的问题，权限与提问的人相同。

国内部署（`--china`，即 `WQO_DEPLOYMENT=cn`）**只用 DeepSeek**（已备案的模型），**不向 Anthropic 发送任何内容**，
即使 `.env` 里有 Anthropic 密钥也一样。启用方法：在 `.env` 里填上企业自己的 DeepSeek API 密钥，然后重启 hub：

```bash
WQO_DEEPSEEK_API_KEY=<您的 DeepSeek API 密钥>
WQO_AI_MODEL=deepseek-chat        # 可选，默认就是 deepseek-chat
```

```bash
docker compose -p wqo up -d hub
```

服务器需要能访问 `api.deepseek.com`。`WQO_AI_PROVIDER` 不用填；如果填了 `deepseek` 以外的值，hub 启动时会报错停下，
说明原因（看 `docker compose -p wqo logs hub`）。

- 模型按提问人的语言回答；它起草的文书按企业语言写。
- 没有密钥时，由内置的规则引擎回答常见问题（也认中文问法）。
- AI 只起草，写入 ERPNext 或对外发送都要人在界面上确认。
- 每次运行（问题、用到的工具、回答、数字核对、token 用量）都留记录，有“配置 AI 助手”权限的人可以查看
  （`GET /api/ai/runs?everyone=true`）。

### 质量记录与签字

关闭不合格品报告、批准需要批准的处置、完成 8D、关闭纠正措施，都要签字：本人再输一次自己的 WenQuest Ops 密码。
签字和质量历史不能修改或删除，在数据库层面也不行（有触发器拒绝）。处置类型（例如需要另一人批准的“让步接收”）
由有“修改平台设置”权限的人维护（`POST /api/quality/dispositions`）。

### 文件库

有“上传文件”权限的人可以把文件、整个文件夹或 zip 包拖到“文件”页面（PDF、Word、Excel、CSV、文本和图片；
每个文件最大 50 MB，每次导入最多 2,000 个文件）。文件存在本服务器的 `hub-files` 卷里，内容相同的只存一份，
每次备份都包括在内。文字在本机提取；扫描页和图片在 hub 镜像里用 Tesseract OCR 识别（简体中文和英文）。
CSV 支持 GBK/GB18030 和 UTF-8。在有人选择“用 AI 分类”之前，不向外发送任何内容；选择之后，每个文件的文字
（长文件取开头、各级标题和结尾）发给企业自己的模型（国内为 DeepSeek），页面会先显示文件数和估计的 token 数。
没有密钥时由规则分类，准确度有限。每条建议都要人确认；程序文件、作业指导书和表单要由上传人、确认人和提交人以外的人
用密码批准后才生效。

容量：按企业要导入的文件夹大小准备磁盘，每保留一份备份再加同样大小（备份是压缩的，但 PDF 和图片几乎压缩不了）。
用模型分类的用量大约是每读 4 个字符 1 个 token，另加每个文件约 1,500 个 token（中文每个字符占的 token 可能更多）。

### 监控

- `https://<域名>/api/health`：数据库、ERPNext 和企业清单都正常时返回 200 和 `{"ok": true, ...}`，否则返回 503
  并写明哪一项失败。可以让监控系统定时访问它。
- `status.sh` 有检查失败时退出码为 1；它也显示剩余磁盘和最新的备份。

## 自己构建镜像（可选）

一般不需要：直接用国内仓库里的镜像即可。如果要在国内自己构建 hub 镜像，`Dockerfile` 支持三个构建参数，
让 npm、pip 和 apt 使用国内源（不填则用默认源）。下面是 `Dockerfile` 注释里的例子，可换成您常用的源：

```bash
docker build --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
             --build-arg PIP_MIRROR=https://mirrors.aliyun.com/pypi/simple/ \
             --build-arg APT_MIRROR=mirrors.aliyun.com \
             -t wenquest-ops-hub:local .
```

构建还需要拉取基础镜像 `node:22-slim` 和 `python:3.12-slim`，它们不在项目复制到国内仓库的镜像之列，
请确保构建机器能拉到（例如通过 Docker 的镜像加速配置）。用自建镜像安装：

```bash
WQO_HUB_IMAGE=wenquest-ops-hub:local ./install.sh --company company.yaml --domain ops.example.cn \
    --email it@example.cn --china --mirror registry.example.cn/wenquest --no-pull
```

`--no-pull` 表示只用本机已有的镜像，所以其他镜像（ERPNext、Caddy 等）需要事先拉到本机；
去掉 `--no-pull` 则会从 `--mirror` 仓库拉取。

## 故障排查

| 现象 | 检查 |
| --- | --- |
| 证书错误、网站打不开 | 域名是否已备案；两个域名是否解析到本服务器；80/443 端口和安全组是否放行；`docker compose -p wqo logs caddy` |
| 拉镜像失败或超时 | 是否加了 `--mirror`；仓库地址和令牌是否正确；`.env` 里的 `WQO_*_IMAGE` 是否都指向国内仓库 |
| `/api/health` 显示 `erpnext: error` | `docker compose -p wqo ps`；ERPNext 重启后需要几分钟 |
| `/api/health` 显示 `database: error` | `docker compose -p wqo logs db`；剩余磁盘 |
| 设置向导失败 | `company.yaml` 里的国家、币种和时区必须是 ERPNext 认的值（`China`、`CNY`、`Asia/Shanghai`） |
| 同步状态显示错误 | 错误里写明了调用的 ERPNext 接口；检查 `.env` 里的 `WQO_ERP_API_KEY` / `SECRET` 和 `/api/health` |
| hub 启动不了，日志提到 DeepSeek | 国内部署只能用 DeepSeek：删掉 `WQO_AI_PROVIDER` 或设为 `deepseek` |
| AI 回答报“连不上模型”或“模型出错” | 密钥是否正确；服务器能否访问 `api.deepseek.com` |
| 界面是英文 | 企业清单里是否有 `language: zh`；个人是否在侧栏切到了 English |
| 内存不足 | ERPNext 至少需要 8 GB；用 `free -h` 查看 |

## 安全事项

- 只有 Caddy 对外开放；数据库和 Redis 只在 Docker 内部网络里。
- `.env`、`company/` 和 `backups/` 里有密码和企业数据：只放在本服务器上，权限 600。
- 没有人确认，WenQuest Ops 不会往 ERPNext 写任何东西（ADR-0001、ADR-0002）。

## 作为模块装在问渠国内服务器上（ADR-0024）

问渠的国内服务器上，WenQuest Ops 由 GitHub Actions 的“Deploy to the WenQuest server in China”自动部署，不需要在服务器上
手工运行 `install.sh`：

1. 目录 `/opt/wenquest/qms` 由部署流程用 deploy 用户自己建，不需要 root；按问渠仓库《国内服务器加模块（质量ERP等）》第二节
   第 5 条生成本模块专用的 SSH 钥匙，填进本仓库的 Secrets `CN_DEPLOY_HOST`、`CN_DEPLOY_SSH_KEY`。
2. 在 GitHub 上手动运行一次该部署流程（以后每次中枢镜像更新后自动运行）。第一次会装好并导入国内演示企业，约 20–30 分钟。
3. 在服务器上设老板（王丹）的密码，并填 DeepSeek 钥匙（都会在终端里问，不显示）：
   ```bash
   cd /opt/wenquest/qms
   ./owner-password.sh
   ./ai-key.sh
   ```
4. 告诉问渠主仓库在 `deploy/caddy-extra/cn/qms.caddy` 里把 `qms.<主域名>` 和 `qms-erp.<主域名>` 都转给 `qms-demo-edge:80`；
   备案号下来、域名解析后即可访问。

这里的装法是 `--china --edge --small --project qms --mirror 127.0.0.1:5000/qms`：不占 80/443，由问渠的 Caddy 办证书；每个容器
有内存上限（合计约 2.4 GB，实测导入演示数据后约 0.9 GB）；镜像从服务器自带的仓库拉。日常命令里的 `-p wqo` 换成 `-p qms`；
`status.sh`、`backup.sh`（每天 04:10 自动，留 7 份）照常可用。
