# 校园点餐系统

这是一个基于 Django 的校园点餐系统，面向校园内的顾客、商家、骑手和平台管理员，提供店铺浏览、商品下单、订单配送、评价、客服工单、数据导入和 AI 问答等功能。

## 技术栈

- Python 3.10+ / 3.12
- Django 5.2.6
- SQLite
- Pillow
- HTML / CSS / Django Templates

## 功能概览

- 顾客端：店铺列表、商品浏览、搜索、购物车、优惠券、收货地址、下单、支付模拟、订单查看、订单评价、商品收藏、站内通知。
- 商家端：商家工作台、商品管理、分类管理、商品上下架、CSV 商品导入、商品图片批量更新、订单管理、销售统计、客服收件箱。
- 骑手端：待接订单、接单、配送状态更新、配送历史、收入统计。
- 管理端：Django Admin、用户批量创建、历史订单导入、评价导入、首页横幅、站点配置。
- 客服模块：用户提交工单，商家或管理员处理工单状态并回复。
- AI 问答：通过后台配置的 AI 服务参数，为登录用户提供点餐相关问答接口。

## 目录结构

```text
order_system_project/
├── import_csv/          # 示例 CSV 数据
├── order_system/        # Django 项目配置
├── shop/                # 点餐系统核心应用
├── site_settings/       # 站点动态配置
├── static/              # 全局静态资源
├── templates/           # 全局模板
├── manage.py
├── requirements.txt
└── README.md
```

## 本地运行

1. 克隆或进入项目目录：

```bash
cd order_system_project
```

2. 创建并激活虚拟环境：

```bash
python -m venv venv
venv\Scripts\activate
```

3. 安装依赖：

```bash
pip install -r requirements.txt
```

4. 执行数据库迁移：

```bash
python manage.py migrate
```

5. 创建超级管理员：

```bash
python manage.py createsuperuser
```

6. 启动开发服务器：

```bash
python manage.py runserver
```

默认访问地址为：

- 前台首页：http://127.0.0.1:8000/
- 管理后台：http://127.0.0.1:8000/admin/

如果需要指定端口：

```bash
python manage.py runserver 127.0.0.1:8080
```

## 后台配置

登录 Django 管理后台后，可以在 `site_settings` 中配置动态参数，例如：

- `SYSTEM_PROMPT`
- `OPENAI_API_KEY`
- `AI_ASSISTANT_URL`

这些配置用于 AI 问答服务。生产环境中请不要把密钥写入代码或提交到仓库。

## CSV 数据导入

项目提供了多类导入能力：

- 商家商品导入：商家端商品导入页面
- 用户批量创建：`/manage/user-batch-create/`
- 历史订单导入：`/manage/order-import/`
- 历史评价导入：`/manage/review-import/`

示例数据位于 `import_csv/` 目录。导入文件建议使用 UTF-8 或 UTF-8 with BOM 编码。

## 常用命令

```bash
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py shell
```

## 开发说明

- 本项目默认使用 SQLite，数据库文件 `db.sqlite3` 不建议提交到仓库。
- 用户上传的图片位于 `media/`，不建议提交到仓库。
- 本地账号密码、`.env`、IDE 配置、虚拟环境等文件已通过 `.gitignore` 忽略。
- 当前项目为开发环境配置，`DEBUG=True`、`ALLOWED_HOSTS=["*"]`、固定 `SECRET_KEY` 不适合直接用于生产环境。

## 验证

当前项目可通过以下命令进行基础检查：

```bash
python manage.py check
```
