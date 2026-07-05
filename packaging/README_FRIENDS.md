# Garmin Coach — setup for friends (macOS)

You need two things you already have: a **Garmin account** and a **Claude
subscription** (Pro or Max). No coding, no API keys.

## Run it

1. **Download** `GarminCoach.zip` and double-click to unzip → you get
   **GarminCoach.app**.
2. **First open:** macOS blocks apps from unidentified developers. **Right-click
   the app → Open → Open** (you only do this once). It's unsigned because we
   didn't pay Apple's developer fee — it's the same app, just not notarized.
3. A browser tab opens with a short **setup page**:
   - **Connect Garmin** — type your Garmin email + password, then the code Garmin
     texts/emails you. (Your password is used once to get a token and is never
     stored.)
   - **Connect Claude** — click the button; a Terminal window opens and signs you
     in to Claude in your browser. Approve it, come back, and it flips to
     ✓ connected.
4. Click **Finish & open dashboard**. It pulls your recent Garmin data and drops
   you into the app.

**Every launch after that goes straight to the dashboard** — the setup page only
appears the first time.

## Notes

- Everything stays **on your Mac** — your data and logins never leave your
  computer. The AI coaching runs on **your** Claude subscription.
- If "Connect Claude" says Claude Code isn't installed, click **Install Claude
  Code** first (it downloads the small helper), then **Connect Claude**.
- First data sync can take a few minutes. Use **↻ Sync now** in the app later to
  pull more history.
- To move it: it's a normal app — drag `GarminCoach.app` to your Applications
  folder if you like.
