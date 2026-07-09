# Run Garmin Coach on an Oracle Cloud "Always Free" VM

Always-on, reachable from your phone anywhere (privately, via Tailscale), running
the **full** app — data, Garmin sync, and the Claude AI — for free. No Docker.

You've created the Oracle account. Do the steps below in order.

---

## Phase 1 — Create the VM (Oracle console, ~15 min)

1. Console → **☰ → Compute → Instances → Create instance**.
2. **Image and shape → Edit shape:**
   - Shape series: **Ampere** → **VM.Standard.A1.Flex** (ARM).
   - Set **2 OCPUs** and **12 GB** memory (well within the free 4 OCPU / 24 GB).
   - Image: **Canonical Ubuntu 22.04**.
   - *If you get "Out of host capacity":* change the **Availability Domain** (AD-1/2/3) and retry, or try again later — it's the known ARM free-tier squeeze.
3. **Networking:** keep the default VCN/subnet, **Assign a public IPv4 address = Yes**.
4. **SSH keys:** choose **Generate a key pair for me** and **download the private key**
   (or paste your own public key). Save the private key somewhere safe.
5. **Create.** When it's **Running**, copy the **Public IP address**.

Connect from your Mac's Terminal (adjust the key path):

```bash
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<VM_PUBLIC_IP>
```

---

## Phase 2 — Run the installer (on the VM, ~15 min)

On the VM shell, fetch and run the installer:

```bash
curl -fsSL https://raw.githubusercontent.com/omri566/garmin-coach/main/packaging/oracle/setup.sh -o setup.sh
bash setup.sh
```

> Private repo? First run `git clone https://github.com/omri566/garmin-coach.git`
> yourself (it'll prompt for a GitHub token), then `bash garmin-coach/packaging/oracle/setup.sh`.
> Or just make the repo public — it's the simplest path.

It installs Python 3.13, the app, the Claude CLI, Tailscale, and the systemd
services, then prints the interactive steps (also listed below).

---

## Phase 3 — Log in to the three accounts (on the VM, ~10 min)

```bash
sudo tailscale up          # open the URL, sign in (free). Install Tailscale on your PHONE too, same login.
claude auth login          # sign in with your Claude subscription (use `claude setup-token` if no browser)
cd ~/garmin-coach
GC_DATA_DIR=$PWD/data .venv/bin/python -m garmin_coach.ingest.sync --limit 1   # Garmin email/password + MFA
```

---

## Phase 4 — Seed data + go live (~5 min + sync time)

**Option A (recommended) — copy your Mac's history.** Run **on your Mac**:

```bash
scp -r ~/programming/garmin-coach/data ubuntu@<VM_PUBLIC_IP>:~/garmin-coach/
```

**Option B — fresh sync on the VM** (slower). Skip the copy; the pipeline below
pulls your history.

Then, back **on the VM**:

```bash
cd ~/garmin-coach
GC_DATA_DIR=$PWD/data .venv/bin/python -m garmin_coach.pipeline   # first full sync + features (+ AI)
sudo systemctl enable --now garmin-coach.service garmin-coach-sync.timer
systemctl status garmin-coach.service --no-pager                 # should say active (running)
```

---

## Phase 5 — Open it on your phone

With Tailscale running on both the VM and your phone:

```bash
echo "http://$(tailscale ip -4):8050"     # run on the VM to get the address
```

Open that URL in your phone's browser — from anywhere, private and free. Bookmark
it / add to Home Screen.

---

## Day-to-day & housekeeping

- **Updates from the DB happen nightly** (the sync timer at 05:30). Trigger one now:
  `sudo systemctl start garmin-coach-sync.service` · logs: `journalctl -u garmin-coach-sync -e`.
- **App logs:** `journalctl -u garmin-coach -e`. **Restart:** `sudo systemctl restart garmin-coach`.
- **Update the code:** `cd ~/garmin-coach && git pull && .venv/bin/pip install -r requirements.txt && sudo systemctl restart garmin-coach`.
- **Stay in the free lane:** don't click "Upgrade to Pay As You Go", and don't add
  resources beyond the Always-Free limits — then it won't cost anything.
- **Idle reclamation:** the nightly sync keeps the VM active; if Oracle ever stops
  it for idleness, just start it again in the console.
- **Security:** never open port 8050 in the Oracle security list. Access is
  Tailscale-only, so your health data is never on a public port.
