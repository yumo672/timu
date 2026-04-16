# 智能采购审批系统

基于 Django 的采购审批演示项目，包含注册登录、采购申请、分级审批、打回重提和审批时间线展示。

## 技术栈

- 后端：Django 4.2 + Django REST framework
- 前端：HTML + CSS + JavaScript
- 数据库：SQLite

## 功能说明

- 申请人可以创建、编辑、提交采购申请，并查看自己的审批进度
- 金额小于 `1000` 元的申请自动通过
- 金额在 `1000` 到 `4999.99` 元之间的申请进入财务审批
- 金额大于等于 `5000` 元的申请需要财务先审、导师再审
- 审批人可以通过或打回申请，打回时必须填写理由
- 被打回的申请可修改后重新提交
- 导师可以查看全部申请状态

## 启动方式

```bash
python -m pip install -r requirements.txt
cd backend
python manage.py migrate
python manage.py runserver
```

启动后访问 `http://127.0.0.1:8000/`。

## 测试

```bash
cd backend
python manage.py test
```
