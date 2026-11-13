# ElDewrito 0.7.1 on PS5 (Playden)

Fixes that let ElDewrito 0.7.1 (Halo Online) start and reach its menus on a
jailbroken PS5 under Playden's Wine, with a controller and a working Settings
screen. The Xbox button prompts, in the original menus and in the web
screens, are also swapped for PS5 ones.

Worked out and tested on Playden 0.11.0-beta.4 (kit 0.25), firmware 12.20.

## How to use it

You need:

- A PC with Python 3 (nothing else to install).
- A clean copy of ElDewrito 0.7.1: the folder that holds `eldorado.exe`.
- This repository, downloaded or cloned as a whole. The script uses
  `dewbridge.dll` and `dualsense_controller.png` from its own folder.
- A PS5 with Playden.

### 1. Patch the game folder on the PC

Open a terminal in this repository's folder and give the script the game
folder:

```
python patch_for_ps5.py "D:\path\to\ElDewrito_0.7.1"
```

It changes the folder in place and prints one line per step. A first run
looks like this:

```
D:\path\to\ElDewrito_0.7.1
  mtndew.dll: patched (original kept as mtndew.dll.orig)
  binkw32.dll: bridge installed (original kept as binkw32_orig.dll)
  dewrito_prefs.cfg: set Game.CEFGpuEnable "0", Settings.Gamepad "1"
  button glyphs: 19 icons replaced with PS5 ones (originals kept in ui\assets\buttons_xbox_orig)
  game menu glyphs: 40 glyphs replaced with PS5 ones in the game's fonts (original kept as font_package.bin.xbox_orig)
  button names: PS5 names in the controller settings (original kept as settings.js.xbox_orig)
  controller picture: DualSense photo, labels moved to match (originals kept as controller.png.xbox_orig, settings.css.xbox_orig)
In Playden, set the program arguments to: --single-process --in-process-gpu
```

What the lines can say:

- `already ...`: that step was done on an earlier run. Running the script
  again is safe; it only does what is missing.
- `... skipped` or `... left alone`: a file was missing or not the one the
  script expects, so that step changed nothing. The other steps still run.
- If the script stops with `mtndew.dll is not the 0.7.1 file this patch was
  made for`, nothing was changed: the folder is not a clean 0.7.1. The script
  checks that file by hash before it touches anything.

### 2. Put it on the PS5

1. Import the patched folder into Playden.
2. In Playden's settings for the game, set the program arguments to:

   ```
   --single-process --in-process-gpu
   ```

   The script cannot set these for you, and the game shows a black screen
   without them.
3. Launch the game.

### Options

| Command | What it does |
| --- | --- |
| `python patch_for_ps5.py "<folder>"` | Applies everything |
| `python patch_for_ps5.py "<folder>" --no-glyphs` | Applies the fixes only, and leaves every Xbox button glyph, button name and the controller picture as they are |
| `python patch_for_ps5.py "<folder>" --undo` | Puts back the original DLLs, `font_package.bin`, button icons, `settings.js`, `settings.css` and controller picture. `dewrito_prefs.cfg` is left as it is |

To go from PS5 glyphs back to Xbox ones while keeping the fixes, run
`--undo` and then run the script again with `--no-glyphs`.

To use your own button art instead of the drawn glyphs, see
[Using your own art](#using-your-own-art). To try the patched folder on the
PC first, see [Testing on a PC](#testing-on-a-pc).

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

## PS5 controls

This part is cosmetic: the game runs without it, and `--no-glyphs` skips it.
The game shows Xbox buttons in the original menus and HUD and in three places
in the web screens, and the script changes each one.

| What | File in the game folder | Becomes | Original kept as |
| --- | --- | --- | --- |
| Button glyphs in the original game's menus and HUD | `maps/fonts/font_package.bin` (40 glyphs) | PS5 glyphs with the same size and spacing | `font_package.bin.xbox_orig` |
| Button icons in web-screen prompts | `ui/assets/buttons/360_*.png` (19 files) | PS5 glyphs, each at the pixel size of the icon it replaces | `ui/assets/buttons_xbox_orig/` |
| Button names in the binding drop-downs of Settings > Controls | `ui/screens/settings/settings.js` | PS5 names | `settings.js.xbox_orig` |
| Controller photo in Settings > Controls | `ui/assets/settings/controller.png` | A photo of a DualSense (`dualsense_controller.png`) | `controller.png.xbox_orig` |
| Places of the labels around that photo | `ui/screens/settings/settings.css` | Rearranged to suit a DualSense | `settings.css.xbox_orig` |

The script draws the glyphs itself; they are approximations of the DualSense
symbols, not official art. The controller photo is a file next to the script
(see [Credits](#credits)).

| Xbox | PS5 |
| --- | --- |
| A, B, X, Y | Cross, Circle, Square, Triangle |
| LB, RB | L1, R1 |
| LT, RT | L2, R2 |
| LS, RS (stick click) | L3, R3 |
| Start | Options |
| Back | Create |

Details:

- The original game prints its button prompts as characters U+E100 and up of
  two fonts (conduit-16 and conduit-18) in `font_package.bin`. Each Xbox
  glyph is overwritten in place by a PS5 one of the same pixel size that
  packs into no more bytes, so nothing else in the file moves. The d-pad
  arrows are plain arrows and stay. In the smaller font the face buttons are
  a ring with a coloured symbol and no dark fill, because the filled ones do
  not fit in the space of the Xbox ones. The format is described in a
  comment in `patch_for_ps5.py`.
- Only the displayed names change in `settings.js`. The page still sends the
  game `A`, `LB` and so on, so bindings and presets work as before. Preset
  names such as "Halo 3 Bumper Jumper" are not changed.
- A DualSense has its d-pad and left stick the other way round from an Xbox
  pad, and its Options button on the right. So that the label lines do not
  cross, nine labels swap places in `settings.css`: Create, Up, Left, Down,
  Right and L3 run down the left side, Options, Triangle, Circle, Cross and
  Square down the right, and R3 sits below. The places themselves are the
  ones the page already had. The photo and the label places are changed
  together or not at all.
- The names assume Back is Create and Start is Options. If Playden maps Back
  to the touchpad instead, that one name is wrong.
- A game folder laid out like ElDewrito 0.6 (`mods/ui/web/assets/buttons`,
  with a second `XboxOne_` icon set) gets its icons replaced too.
- If a file is missing or not as expected, the script says so and leaves it
  alone.

### Using your own art

Put PNGs in a `ps5_glyphs` folder next to the script; each one found is used
instead of the drawn version.

- Button icons are named after the Xbox button: `A.png`, `B.png`, `X.png`,
  `Y.png`, `LB.png`, `RB.png`, `LT.png`, `RT.png`, `LS.png`, `RS.png`,
  `LS_Click.png`, `RS_Click.png`, `Start.png`, `Back.png`, `Dpad.png`,
  `Dpad_Up.png`, `Dpad_Down.png`, `Dpad_Left.png`, `Dpad_Right.png`. The
  stock icons are 100 to 136 pixels square.
- `controller.png` replaces the DualSense photo. Make it 1024x670 with its
  label lines ending where those of `dualsense_controller.png` do, or the
  labels will not line up. `make_controller_pic.py` shows how that picture
  was built and holds the line positions.

## Files

| File | What it is |
| --- | --- |
| `patch_for_ps5.py` | Applies everything above to a chosen game folder; `--undo` reverses it, apart from the settings |
| `dewbridge.dll` | The compiled bridge the script installs |
| `dualsense_controller.png` | The DualSense photo, cut out and with label lines, that the script installs |
| `make_controller_pic.py` | Rebuilds `dualsense_controller.png` from the original photo; needs Pillow |
| `dewbridge.c` | The bridge's source |
| `build.sh` | Builds the bridge |
| `patch_base.py` | Older script with only the `mtndew.dll` patch; superseded by `patch_for_ps5.py` |
| `start-ps5-mode.bat` | Copy into the game folder; starts the PC copy with the PS5 arguments. Add `debug` for Chrome DevTools on `http://127.0.0.1:8884` |
| `ps5_glyphs/` | Optional, not included: your own PNGs to use instead of the drawn glyphs |

## Credits

`dualsense_controller.png` is adapted from
["DualSense Controller Chroma Pearl.jpg"](https://commons.wikimedia.org/wiki/File:DualSense_Controller_Chroma_Pearl.jpg)
by Sonson2 on Wikimedia Commons, licensed
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). The
background was removed, the picture scaled, and label lines added. The
adapted picture is under the same licence; the rest of this repository is
under the licence in `LICENSE`.

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
web UI can be reproduced there. With `start-ps5-mode.bat` copied into the
patched game folder:

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
- The PS5 glyphs in the original game's menus (the patched
  `font_package.bin`) were seen working in the Forge Lobby on a PC copy of
  0.7.1, not yet on the console. If the menus misbehave there, `--undo` puts
  the original back.
- The web-screen icons, the names, the controller photo and the label places
  were checked as files on that PC copy; they have not been seen in the
  running game or on the console.
- Text that names an Xbox button in words, in the original game's strings, is
  not changed. PNGs in `ps5_glyphs` do not apply to the game's fonts.
- When a page closes, the bridge does not tell the game to cancel that page's
  unanswered requests; late answers are dropped.
- `crash_reporter.exe` cannot run on PS5, so a game crash leaves a
  `crash_dump.json` and no report window.
- Files the game creates on the console are private to it; a payload cannot
  read `dewbridge.log` or `logs/` there. Use Playden's log export instead,
  with the game's Logging set to verbose, and keep the run short: the export
  drops the middle of a long log.
