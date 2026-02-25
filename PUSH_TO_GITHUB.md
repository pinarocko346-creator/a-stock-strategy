# 推送到 GitHub 说明

本目录已初始化为 Git 仓库，并已关联远程：

- **远程地址**: https://github.com/pinarocko346-creator/a-stock-strategy.git  
- **当前分支**: `main`  
- **已提交**: 抄底波段222 选股脚本、README、requirements、.gitignore  

## 你需要在有网络的环境下执行

在 **PowerShell** 或 **命令提示符** 中：

```powershell
cd C:\Users\luohy\a-stock-strategy
git push -u origin main
```

若 GitHub 上该仓库是新建且为空，会直接推送成功。

若 GitHub 上已有内容（例如有 README），需先拉再推：

```powershell
git pull origin main --allow-unrelated-histories
# 若有冲突，解决后：
git add .
git commit -m "merge"
git push -u origin main
```

若仓库默认分支是 `master` 而不是 `main`，可改为：

```powershell
git push -u origin main:master
```

## 首次在 GitHub 创建仓库时

1. 打开 https://github.com/new  
2. 仓库名填：`a-stock-strategy`  
3. 选择 **Public**，不要勾选 “Add a README”（保持空仓库）  
4. 创建后，在本地执行上面的 `git push -u origin main` 即可。
