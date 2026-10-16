"""
Vibrance - digital vibrance (screen saturation) for Steam Deck, like NVIDIA Digital Vibrance.

How it works: gamescope "looks" - a 3D LUT applied by the compositor on top of everything
(games and Steam UI) in gamma 2.2 space. Valve uses the same mechanism for the built-in
greyscale / colour-blind filters. We generate a saturation LUT and load it with
`gamescopectl set_look`.

Scale (NVIDIA): 50 = unchanged, 0 = greyscale, 100 = twice as saturated. Greys stay grey.
"""

import asyncio
import json
import os
import subprocess

import decky

N = 17                               # LUT grid, same as gamescope's hardware 3D LUT
LUMA = (0.2126, 0.7152, 0.0722)      # Rec.709 - same weights as Valve's grayscale_g22.cube
DEFAULTS = {"level": 70, "enabled": True, "lang": "auto"}
LANGS = ("auto", "ru", "en")

SETTINGS = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")
LUT_DIR = decky.DECKY_PLUGIN_RUNTIME_DIR


def build_lut(level: int) -> str:
    s = level / 50.0
    lines = [f'TITLE "Vibrance {level}"', f"LUT_3D_SIZE {N}"]
    for b in range(N):
        for g in range(N):
            for r in range(N):          # red changes fastest (standard .cube order)
                c = (r / (N - 1), g / (N - 1), b / (N - 1))
                y = LUMA[0] * c[0] + LUMA[1] * c[1] + LUMA[2] * c[2]
                v = [min(max(y + (x - y) * s, 0.0), 1.0) for x in c]
                lines.append("%.6f %.6f %.6f" % tuple(v))
    return "\n".join(lines) + "\n"


def runtime_dir() -> str:
    uid = os.getuid()
    return f"/run/user/{1000 if uid == 0 else uid}"


def system_env() -> dict:
    # Decky is a PyInstaller bundle and points LD_LIBRARY_PATH at its own old libstdc++,
    # which breaks system binaries (gamescopectl: GLIBCXX_3.4.31 not found). Restore the original.
    env = {k: v for k, v in os.environ.items() if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD")}
    if os.environ.get("LD_LIBRARY_PATH_ORIG"):
        env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH_ORIG"]
    env["XDG_RUNTIME_DIR"] = runtime_dir()
    return env


class Plugin:
    settings = dict(DEFAULTS)
    watcher = None
    lock = None

    def load(self):
        try:
            with open(SETTINGS) as f:
                data = json.load(f)
            self.settings = {
                "level": max(0, min(100, int(data.get("level", DEFAULTS["level"])))),
                "enabled": bool(data.get("enabled", DEFAULTS["enabled"])),
                "lang": data.get("lang") if data.get("lang") in LANGS else "auto",
            }
        except Exception:
            self.settings = dict(DEFAULTS)

    def save(self):
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        tmp = SETTINGS + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.settings, f)
        os.replace(tmp, SETTINGS)

    async def apply(self) -> bool:
        level = self.settings["level"] if self.settings["enabled"] else 50
        os.makedirs(LUT_DIR, exist_ok=True)
        path = os.path.join(LUT_DIR, "vibrance.cube")
        tmp = path + ".tmp"
        with open(tmp, "w") as f:       # write fully, then swap - gamescope never sees a half file
            f.write(build_lut(level))
        os.replace(tmp, path)

        # Plain blocking call (takes milliseconds). asyncio subprocesses hang inside _unload,
        # where Decky is already tearing the event loop down.
        try:
            res = subprocess.run(["gamescopectl", "set_look", path], env=system_env(),
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=2)
            text = res.stdout.decode(errors="replace").strip()
            ok = res.returncode == 0 and "error" not in text.lower() and "not found" not in text.lower()
            if not ok:
                decky.logger.warning(f"gamescopectl set_look failed ({res.returncode}): {text}")
            return ok
        except Exception as e:
            decky.logger.warning(f"gamescopectl set_look failed: {e}")
            return False

    def gamescope_id(self):
        # The control socket is recreated whenever gamescope restarts (Steam restart, mode switch)
        try:
            st = os.stat(os.path.join(runtime_dir(), "gamescope-0"))
            return (st.st_ino, st.st_mtime_ns)
        except OSError:
            return None

    async def watch(self):
        # Re-apply after gamescope (re)starts; until the first success keep retrying
        applied_for = None
        while True:
            try:
                gid = self.gamescope_id()
                if gid is not None and gid != applied_for:
                    await asyncio.sleep(2)              # let gamescope finish starting
                    async with self.lock:
                        if await self.apply():
                            applied_for = gid
            except asyncio.CancelledError:
                raise
            except Exception as e:
                decky.logger.warning(f"watch: {e}")
            await asyncio.sleep(3)

    # ---- frontend API ----

    async def get_state(self) -> dict:
        return dict(self.settings)

    async def set_state(self, level: int, enabled: bool) -> bool:
        self.settings = dict(self.settings, level=max(0, min(100, int(level))), enabled=bool(enabled))
        self.save()
        async with self.lock:
            return await self.apply()

    async def set_lang(self, lang: str) -> bool:
        self.settings = dict(self.settings, lang=lang if lang in LANGS else "auto")
        self.save()
        return True

    # ---- lifecycle ----

    async def _main(self):
        self.lock = asyncio.Lock()
        self.load()
        self.watcher = asyncio.get_event_loop().create_task(self.watch())
        decky.logger.info(f"Vibrance started: {self.settings}")

    async def _unload(self):
        decky.logger.info("unload: start")
        if self.watcher:
            self.watcher.cancel()
        # Plugin disabled / Decky stopping - neutral colours
        saved = self.settings
        self.settings = dict(saved, level=50, enabled=False)
        ok = await self.apply()
        self.settings = saved
        decky.logger.info(f"unload: neutral applied={ok}")

    async def _uninstall(self):
        self.settings = dict(self.settings, level=50, enabled=False)
        await self.apply()
