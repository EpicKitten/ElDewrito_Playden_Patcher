# ElDewrito 0.7.1 on PS5 (Playden)

Fixes that let ElDewrito 0.7.1 (Halo Online) start and reach its menus on a
jailbroken PS5 under Playden's Wine, with a controller and a working Settings
screen.

Worked out and tested on Playden 0.11.0-beta.4 (kit 0.25), firmware 12.20.

## Quick start

1. On a PC, patch a clean ElDewrito 0.7.1 folder:

   ```
   python patch_for_ps5.py "D:\path\to\ElDewrito_0.7.1"
   ```

2. Import that folder into Playden.
3. In Playden's settings for the game, set the program arguments to:

   ```
   --single-process --in-process-gpu
   ```

4. Launch.

Run the script again at any time; it skips what is already done. To put the
original DLLs back:

```
python patch_for_ps5.py "D:\path\to\ElDewrito_0.7.1" --undo
```

The script needs Python 3 and nothing else. It only accepts the exact 0.7.1
`mtndew.dll` (checked by hash) and stops before changing anything if the file
is different.

## What is wrong, and what each fix does

Playden's Wine on PS5 differs from Windows in three ways that matter here.

| Problem on PS5 | Symptom | Fix |
| --- | --- | --- |
| A module snapshot of the game's own process fails (`CreateToolhelp32Snapshot` / `Module32First`) | Crash two seconds after launch, `c0000409` in `mtndew.dll` | `mtndew.dll` patched to use the base address `0x400000` directly |
| No process can be started | Black screen: the web UI's helper processes (`custom_menu.exe`) never run | Launch arguments `--single-process --in-process-gpu`, plus the bridge DLL |
| The GPU hand-off of the web UI's picture does not draw | Settings blurs the screen but no window appears | `Game.CEFGpuEnable "0"` in `dewrito_prefs.cfg` |

### The `mtndew.dll` patch

ElDewrito finds where `eldorado.exe` is loaded by taking a module snapshot.
When that fails it uses 0, patches the game at addresses 0x400000 too low,
and aborts. The patch changes six places (7 bytes each) to use `0x400000`,
which is the address `eldorado.exe` always loads at. The original is kept as
`mtndew.dll.orig`.

### The bridge (`dewbridge.dll`, installed as `binkw32.dll`)

ElDewrito's menus that are not part of the original game (Settings, server
browser, console, chat) are web pages in an embedded browser (CEF, Chromium
101). The pages call the game through `window.dewQuery`. That function is
normally installed by `custom_menu.exe` running as the browser's renderer
process. In single-process mode it never runs, so the pages load but cannot
talk to the game.

The bridge takes the place of `binkw32.dll` and forwards all 79 Bink video
functions to the real one, renamed `binkw32_orig.dll`. When the game starts
the browser, the bridge puts itself in front of the game's page-side handler
and installs `window.dewQuery` and `window.dewQueryCancel`, using the message
format the game already listens for. Every other call is passed to the game's
own handler unchanged.

It writes a few lines to `dewbridge.log` in the game folder on each start, and
the same lines to the debug output, which Playden's verbose log shows.

### The settings

`data/dewrito_prefs.cfg` gets:

- `Game.CEFGpuEnable "0"`: draw the web UI in software.
- `Settings.Gamepad "1"`: controller support.

## Files

| File | What it is |
| --- | --- |
| `patch_for_ps5.py` | Applies everything above to a chosen game folder; `--undo` reverses the DLL changes |
| `dewbridge.dll` | The compiled bridge the script installs |
| `dewbridge.c` | The bridge's source |
| `build.sh` | Builds the bridge |
| `patch_base.py` | Older script with only the `mtndew.dll` patch; superseded by `patch_for_ps5.py` |
| `..\start-ps5-mode.bat` | Starts the PC copy with the PS5 arguments; add `debug` for Chrome DevTools on `http://127.0.0.1:8884` |

## Building the bridge

In WSL or Linux with `clang-18`, `lld-link-18`, `llvm-dlltool-18` and Python 3:

```
sh build.sh /path/to/original/binkw32.dll
```

It writes `binkw32.dll` next to itself; copy that over `dewbridge.dll`. The
build is 32-bit, has no C runtime and imports only `KERNEL32.dll`. It needs
the original Bink DLL to generate the list of functions to forward.

The struct layouts in `dewbridge.c` follow CEF branch 4951. The game ships a
custom CEF build, so the bridge checks the size of every browser object it is
handed and switches itself off, with a line in the log, if one differs.

## Testing on a PC

The PC copy behaves the same way in single-process mode, so problems with the
web UI can be reproduced there:

```
start-ps5-mode.bat debug
```

Then open `http://127.0.0.1:8884` in a Chromium browser to inspect the pages.
`typeof window.dewQuery` should be `function`.

## Known limits

- Tested: start-up, the main menu, the controller, the Settings screen.
- Not tested: the server browser, console, chat, scoreboard, an actual match,
  online play. The log shows the DNS library failing to load on PS5, so
  anything needing name lookups may not work.
- When a page closes, the bridge does not tell the game to cancel that page's
  unanswered requests; late answers are dropped.
- `crash_reporter.exe` cannot run on PS5, so a game crash leaves a
  `crash_dump.json` and no report window.
- Files the game creates on the console are private to it; a payload cannot
  read `dewbridge.log` or `logs/` there. Use Playden's log export instead,
  with the game's Logging set to verbose, and keep the run short: the export
  drops the middle of a long log.
