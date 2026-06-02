# GitHub Submit Commands

Target repository:

```text
https://github.com/xiejhhhhhh/Draftpaper_CLI.git
```

Recommended commands from `C:\DraftPaper_CLI`:

```powershell
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/xiejhhhhhh/Draftpaper_CLI.git
git push -u origin main
```

GitHub CLI check:

```powershell
gh --version
gh auth status
gh repo view xiejhhhhhh/Draftpaper_CLI
```

Current note: `gh` is installed, but this machine is not logged in yet. Run:

```powershell
gh auth login
```

Then rerun:

```powershell
git push -u origin main
```
