# Publish the reviewed local commit

The GitHub connector can identify the account but cannot create a repository. Local Git publishing credentials remain unavailable. Complete these steps in PowerShell; never paste tokens into chat.

```powershell
winget install --id GitHub.cli --exact --source winget
```

Open a new PowerShell terminal so PATH includes GitHub CLI:

```powershell
cd D:\comguopensource
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
gh api user --jq .login
```

The last command must print `karatarassul4-max`. Then publish the already-reviewed commit:

```powershell
git status --short
gh repo create karatarassul4-max/opencinema-studio --public --source . --remote origin --push --description "Local cinematic image-to-video Studio powered by real ComfyUI and LTX-Video workflows"
```

If the repository already exists, inspect it first instead of overwriting it. Do not force-push. For a confirmed empty repository with no origin configured:

```powershell
git remote add origin https://github.com/karatarassul4-max/opencinema-studio.git
git push -u origin master
```

Verify anonymously (these calls use no GitHub auth headers):

```powershell
$repo = Invoke-RestMethod 'https://api.github.com/repos/karatarassul4-max/opencinema-studio'
$repo | Select-Object full_name, private, html_url
(Invoke-WebRequest 'https://github.com/karatarassul4-max/opencinema-studio').StatusCode
```

Require `private = False` and HTTP 200. Then verify README, license, screenshot, workflows and submission documents at the public URL. Replace the pending repository field in `FINAL-SUBMISSION.md` with the verified link. Do not submit the hackathon form until the owner explicitly approves the completed submission.
