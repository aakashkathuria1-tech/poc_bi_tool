# Drive this Windows machine from your phone

Goal: work from the Claude app on your phone, with **everything actually
running on your Windows PC** — its filesystem, its SSH keys, its VPN routes,
its database clients. Your phone is the steering wheel, not the engine.

That is what **Remote Control** does. This guide sets it up.

---

## Which mode you want

Claude Code offers three ways to work from a phone. They differ in *where the
code runs*, and that difference is the whole decision.

| Mode | Runs on | Reaches your internal servers | Survives PC off |
| --- | --- | --- | --- |
| **Remote Control** | **Your Windows PC** | **Yes** — inherits VPN, SSH keys, mapped drives | No |
| Claude Code on the web | Anthropic cloud | Only if publicly reachable | Yes |
| Dispatch | Desktop app on your PC | Yes | No |

**Use Remote Control** when the work needs your machine or the servers behind
it. Use cloud sessions when you want a task to keep running with your PC off
and everything it touches is on GitHub.

They are not exclusive — run both. The PR work in this repo happens fine in a
cloud session; anything touching your servers wants Remote Control.

---

## One-time setup

### 1. Run the setup script

From this repo on your Windows machine:

```powershell
.\scripts\setup_claude_code.ps1
```

It installs Claude Code and Git for Windows, then preflights the conditions
Remote Control requires. Pass `-Fix` to also clear the environment variables
that silently disable it:

```powershell
.\scripts\setup_claude_code.ps1 -Fix
```

> If PowerShell refuses to run the script, allow local scripts for your user
> once: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

<details>
<summary>What it does, if you would rather do it by hand</summary>

```powershell
# Install Claude Code (auto-updates in the background afterwards)
irm https://claude.ai/install.ps1 | iex

# Optional but recommended - enables the Bash tool instead of PowerShell-only
winget install --id Git.Git

claude --version
claude doctor
```
</details>

### 2. Sign in

Remote Control requires a **claude.ai account** on Pro, Max, Team or
Enterprise. An API key will not work.

```powershell
claude
```

then inside the session:

```
/login
```

Accept the workspace-trust prompt. **Do this from this project directory** —
trust is never saved for your home directory, and Remote Control needs it.

### 3. Get the app on your phone

Inside a `claude` session:

```
/mobile
```

Scan the QR code, or install directly:
[iOS](https://apps.apple.com/us/app/claude-by-anthropic/id6473753684) ·
[Android](https://play.google.com/store/apps/details?id=com.anthropic.claude)

Sign in with the **same account and organization**.

### 4. Turn on push notifications

Inside a `claude` session:

```
/config
```

Enable **Push when Claude decides** (long tasks finishing) and **Push when
actions required** (permission prompts and questions). Without these you have
to keep opening the app to see whether Claude is waiting on you.

You can also ask for one inline: *"notify me when the tests finish"*.

---

## Daily use

On the Windows machine:

```powershell
.\scripts\start_remote_control.ps1
```

Then on your phone: open the Claude app → **Code** tab → pick the session by
name. It shows a computer icon with a green dot when online. Or press
**SPACE** in the terminal window to display a QR code and scan it.

Useful flags:

```powershell
.\scripts\start_remote_control.ps1 -Name "BI tool"   # custom session title
.\scripts\start_remote_control.ps1 -Continue         # resume the last session
.\scripts\start_remote_control.ps1 -Worktree         # isolate parallel sessions
```

### Why the script holds your PC awake

Remote Control is a **local process**. If Windows sleeps, the process stops
and the session ends — you would pick up your phone to find it dead. The
script holds a system-required lock for exactly as long as it runs, then
releases it. The display is still allowed to sleep.

Two consequences worth knowing:

- **Closing the terminal window ends the session.** Leave it open.
- **Being offline for ~10 minutes ends the session.** It times out and the
  process exits; start it again.

If you would rather manage power yourself, pass `-AllowSleep`.

### Start it automatically at logon

To have the session come up whenever you log in, register a scheduled task
(run once, as your normal user):

```powershell
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoExit -ExecutionPolicy Bypass -File `"$PWD\scripts\start_remote_control.ps1`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName 'ClaudeRemoteControl' -Action $action -Trigger $trigger
```

Remove it later with `Unregister-ScheduledTask -TaskName 'ClaudeRemoteControl'`.

> This runs at *logon*, so the machine must be logged in — it is not a
> service. Claude Code has no supported service mode, and running an agent
> with your credentials under an unattended account is a bad trade.

---

## Reaching your servers through this machine

This is the part cloud sessions cannot do. Because Claude Code runs on your
Windows box, it reaches **whatever that box can reach** — no extra
configuration needed for the network path itself:

- Hosts behind your **VPN**, while the VPN is connected
- Servers your **SSH keys** already authenticate to
- **Mapped network drives** and UNC paths
- **Databases** on your internal network, via whatever client is installed

So the setup is ordinary Windows admin, not Claude configuration.

### SSH

Windows 10/11 ship OpenSSH. Confirm and set up a key:

```powershell
ssh -V
ssh-keygen -t ed25519 -C "you@example.com"
type $env:USERPROFILE\.ssh\id_ed25519.pub    # add this to the server
```

Define your hosts in `%USERPROFILE%\.ssh\config` so both you and Claude can
use short names:

```
Host bi-prod
    HostName 10.0.0.42
    User deploy
    IdentityFile ~/.ssh/id_ed25519
```

Then from your phone you can ask for things like *"ssh into bi-prod and check
the disk usage"* and it runs from your PC, over your network, with your key.

Use an **ssh-agent** so Claude is not prompted for a passphrase mid-task:

```powershell
Start-Service ssh-agent
Set-Service ssh-agent -StartupType Automatic
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

### Databases

Install the client you need (`sqlcmd`, `psql`, `mysql`) and put connection
details in environment variables rather than in the repo. To swap this
project's CSV loaders for a live database, replace the `pd.read_csv` calls in
`src/poc_bi/data.py` with `pd.read_sql` — `DataPaths` is the seam, and
everything downstream is unchanged.

### Viewing the dashboard on your phone

The Streamlit app binds to localhost by default, so your phone cannot see it.
Bind it to the LAN instead:

```powershell
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Allow it through the firewall once (as Administrator):

```powershell
New-NetFirewallRule -DisplayName "Streamlit 8501" -Direction Inbound `
    -LocalPort 8501 -Protocol TCP -Action Allow -Profile Private
```

Then open `http://<your-pc-ip>:8501` on your phone, on the same network. Find
the IP with `ipconfig`.

> Scope the rule to `-Profile Private` as above, and do not open 8501 to the
> internet. The app has no authentication.

---

## Security worth understanding before you start

Remote Control gives a phone the ability to drive an agent that holds **your
credentials on your machine**. That is the point of it, and it is also the
risk. Two things follow:

- **Permission mode matters more here.** From the app you can pick Manual,
  Accept edits, or Plan. You cannot select Bypass permissions from a phone,
  which is deliberate — leave it that way.
- **The transcript is stored on Anthropic servers** while Remote Control is
  connected, to keep devices in sync and survive reconnects. Execution and
  file access stay local. If that is not acceptable for a given repo, use a
  local session without Remote Control for it.

Your machine makes **outbound HTTPS only** — no inbound ports are opened, so
this does not expose your PC to the internet.

---

## Troubleshooting

| Message | Cause and fix |
| --- | --- |
| `Remote Control requires a claude.ai subscription` | Signed in with an API key. Run `claude auth login`, and unset `ANTHROPIC_API_KEY`. |
| `Remote Control requires a full-scope login token` | You used `claude setup-token` or `CLAUDE_CODE_OAUTH_TOKEN`. Run `claude auth login` instead. |
| `Remote Control is not yet enabled for your account` | Rollout or stale entitlements. `claude auth logout` then `claude auth login`. `claude doctor` names the failing check. |
| `Remote Control requires feature-flag evaluation` | One of `DISABLE_TELEMETRY`, `DO_NOT_TRACK`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `DISABLE_GROWTHBOOK` is set. Run `.\scripts\setup_claude_code.ps1 -Fix`. |
| `Remote Control is only available when using Claude via api.anthropic.com` | `ANTHROPIC_BASE_URL` points at a gateway/proxy, or a Bedrock/Vertex variable is set. Unset it. |
| `Remote Control is disabled by your organization's policy` | On Team/Enterprise an Owner must enable the Remote Control toggle at claude.ai/admin-settings/claude-code. |
| `Remote credentials fetch failed` | Re-run as `claude remote-control --verbose`. Usually not signed in, or a firewall blocking outbound HTTPS on 443. |
| Session died while you were away | The PC slept, the terminal closed, or it was offline ~10 min. Start the script again. |
| No **Code** tab in the app | Your plan or organization does not include it. |
| `/config` shows **No mobile registered** | Open the Claude app once so it refreshes its push token. |
| Pushes delayed on Android | Exempt the Claude app from battery optimization. |
| Pushes missing on iOS | Check Focus modes and notification summaries under Settings → Notifications → Claude. |

Notifications are also skipped while you are typing in the connected terminal
— that is intentional, not a fault.

---

## Commands that work from the phone

Most do. The exceptions are terminal-only pickers such as `/plugin` and
`/resume`. Some take an argument instead of opening a picker:

```
/model sonnet
/effort high
/config key=value
/compact
/context
```

---

## Sources

- [Remote Control](https://code.claude.com/docs/en/remote-control)
- [Claude Code on mobile](https://code.claude.com/docs/en/mobile)
- [Claude Code on the web](https://code.claude.com/docs/en/claude-code-on-the-web)
- [Advanced setup](https://code.claude.com/docs/en/setup)
