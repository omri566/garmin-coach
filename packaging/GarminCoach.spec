# PyInstaller spec — builds GarminCoach.app (macOS, unsigned).
# Build:  .venv/bin/pyinstaller packaging/GarminCoach.spec --noconfirm
from PyInstaller.utils.hooks import collect_all

# Heavy web/data packages ship JS/CSS/metadata as package data — collect it all
# so Dash, Mantine, Plotly and the Garmin client work inside the frozen app.
_PKGS = [
    "dash", "dash_mantine_components", "plotly",
    "dash_core_components", "dash_html_components", "dash_table",
    "garminconnect", "garth", "garmin_coach",
]
datas, binaries, hiddenimports = [], [], []
for pkg in _PKGS:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# The dashboard's own assets aren't Python package data, so add them explicitly
# at the path Dash expects to find them inside the bundle.
datas += [("../garmin_coach/dashboard/assets", "garmin_coach/dashboard/assets")]

hiddenimports += ["pandas", "numpy", "pyarrow", "dotenv"]

a = Analysis(
    ["../garmin_coach/desktop.py"],
    pathex=[".."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PySide6", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="GarminCoach",
    console=False,          # windowed (double-click) app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,       # native arch of the build machine
)
coll = COLLECT(exe, a.binaries, a.datas, name="GarminCoach")

app = BUNDLE(
    coll,
    name="GarminCoach.app",
    icon=None,
    bundle_identifier="com.garmincoach.app",
    info_plist={
        "CFBundleName": "Garmin Coach",
        "CFBundleDisplayName": "Garmin Coach",
        "NSHighResolutionCapable": True,
        "LSBackgroundOnly": False,
    },
)
