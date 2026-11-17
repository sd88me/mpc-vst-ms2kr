# MS2KR 0.2.0

MS2KR gets a new native MPC screen modelled on the MS2000R's front panel, with RANDOM and named favourites. The sound is unchanged: it is
still the synthesizer's own firmware running on an emulated H8S and DSP56362.

## What's new
- **A new screen, 6 pages** (PLAY, BANKS, OSC, FILTER / EG, LFO / FX / PATCH, ARP / SEQ), drawn like the panel: knurled knobs on printed scales,
  black and cream keys, the 16 square program keys, and one green LCD that shows the firmware's own two lines with the engine status under them.
  The second, boxed names on the panel (the vocoder functions) are printed only where they differ from the main name.
- **The 16 program keys work as on the hardware**: outside EDIT they pick program 1-16 of the current bank, in EDIT they pick the edit page. The
  PROGRAM readout, the bank tiles and the favourites menu now follow a program picked this way (they did not before).
- **RANDOM** (PLAY and BANKS): a random program.
- **Named favourites**: **+FAV** opens an on-screen keyboard with the sound's name (up to 20 characters); edit it and SAVE. Favourites are in MPC's
  PRESET list. Favourites made with 0.1.0 are kept.
- **BANKS**: the selected bank and program stay lit with their names visible.
- **Projects now restore their sound**: a project saved with 0.1.0 (or 0.2.0) that is opened before the machine has booted comes back with its
  program and edited sound; before, the program change and edit were never sent to the machine and the project could open on A01.
- The parameter order is unchanged, so automation and Q-Link assignments from 0.1.0 projects carry over.

## Install
- `MS2KR-0.2.0-mpc-aarch64.zip`: run `install.sh` on the device as root (or use the Plugin Manager). A 0.1.0 install is upgraded in place; your ROMs,
  the machine's stored programs and your favourites are kept.
- `MS2KR-0.2.0-mpc-sdk.zip`: copy the folder `sd88me - VST - MS2KR` into a `VST2 Plugins` folder on a drive of the MPC and put your ROM dumps
  (`flash.bin`, `boot-362.bin`) in its `Content/roms/`. Needs Preferences → Enhancements (Beta) → Enable Enhancements and External Plugin
  Support switched on.

Use one of the two, not both. 64-bit MPCs only (Live III and others); the Force and the 32-bit MPCs are not supported.
Your own MS2000 / MS2000R ROM dumps are required and not included.

## Notes
- Tested on an MPC Live III as a beta build with its own uid (loaded, every page, tiles); the final skin tweaks after that (lit tiles, the panel
  labels) are not separately device-tested. A 0.1.0 project was tested offline with a real 0.1.0 project chunk; loading one on the device,
  save/reload on the device and the install.sh upgrade were not tried before this release.
- A few dropouts can still happen when stepping through programs very fast; the status line under the LCD shows the dropout count.
