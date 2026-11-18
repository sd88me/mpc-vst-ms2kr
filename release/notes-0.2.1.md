# MS2KR 0.2.1

A packaging release: the sound engine and the screens are the same as 0.2.0.

## What's new
- **Your ROMs in the OpenMPC Plugin Manager**: MS2KR's page in the manager now has a "Your ROMs and files" step for the dumps MS2KR needs.
  The 1 MB main flash is saved as `flash.bin` whatever its file name; the 768-byte DSP boot ROM is kept under its own name, `boot-362.bin`
  or the corrected copy `boot-362.ms2000.bin` (used first when both are there). They go in `Content/roms/`.
- **Favourites survive the installer**: `Content/favourites.dat` is now listed as your data in the `install.sh` zip too (the catalog zip
  already kept it), so an upgrade or uninstall no longer drops your favourites.
- **README**: install steps per format (SDK folder or `install.sh`, by hand or with the Plugin Manager), and a section on backing up your
  favourites, programs and ROMs.

## Install
- `MS2KR-0.2.1-mpc-aarch64.zip`: run `install.sh` on the device as root (or use the Plugin Manager). An older install is upgraded in place; your
  ROMs, the machine's stored programs and your favourites are kept.
- `MS2KR-0.2.1-mpc-sdk.zip`: copy the folder `sd88me - VST - MS2KR` into a `VST2 Plugins` folder on a drive of the MPC and put your ROM dumps
  (`flash.bin`, `boot-362.bin`) in its `Content/roms/`. Needs Preferences → Enhancements (Beta) → Enable Enhancements and External Plugin
  Support switched on.

Use one of the two, not both. 64-bit MPCs only (Live III and others); the Force and the 32-bit MPCs are not supported.
Your own MS2000 / MS2000R ROM dumps are required and not included.
