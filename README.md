# KARUSELKA

Fast camera turntable rig for Blender. Pick an object, press **Create Rig** —
a camera orbits it on linear keyframes, ready to scrub or render as a showreel
turntable.

Pairs with [LAMPOCHKA](https://github.com/abyrvalg379/lampochka):
light preset + KARUSELKA turntable = model showcase in two minutes.

## Features

- One click: pivot empty + orbit camera + keyframes, live immediately
- The rig camera becomes the active scene camera (Numpad 0 / render);
  Remove Rig puts your previous active camera back
- Constant rotation speed — interpolation is forced to LINEAR
  (bezier easing is the classic turntable mistake)
- Auto radius from the object size (safe framing on a 50 mm lens), or set your own
- Fractional rounds: 1.5 turns, 2.75, whatever
- CW / CCW direction
- Uses your camera or creates its own (50 mm, DoF off, near/far clip
  sized to the orbit so small and huge models stay in view)
- **Render Turntable** — non-blocking animation render to `//turntable/`
- **Remove Rig** deletes only what KARUSELKA created; your camera survives
- One rig at a time: repeating Create Rig rebuilds it, never stacks

## Install

- Blender 4.2+ — Edit > Preferences > Add-ons > Install from Disk (arrow menu)
  > `karuselka_extension.zip`
- Blender 3.6 – 4.1 — same dialog, `karuselka_legacy.zip`

## Usage

1. N-panel > **KARUSELKA** > pick a Target (or just select an object)
2. **Create Rig** — the camera is already orbiting, scrub the timeline
3. **Render Turntable** — renders frames `1..N` to the output path

### Parameters

| Parameter | Meaning |
|-----------|---------|
| Target | object to orbit around (falls back to the active object) |
| Camera | yours, or auto-created |
| Frames | frames per full revolution; fps comes from the scene |
| Rounds | revolutions, fractional allowed |
| Radius | orbit radius; 0 = auto (object size × 1.5) |
| Height | camera height relative to the object center |
| Dir | orbit direction viewed from above |
| Output | render path, default `//turntable/` |

### Notes

- Render Turntable sets the scene frame range to `1..N` and leaves it visible
  in the timeline; engine, samples and format settings are not touched.
- With your own camera KARUSELKA parents it to the pivot and aims it;
  Remove Rig detaches it again (keeps the world transform).
- Keyframes live on the pivot (`rotation_euler.z`, frame 1 → frame N);
  tweak speed by editing Frames/Rounds and re-running Create Rig.

## License

GPL-3.0-or-later — see [LICENSE](LICENSE). © Maksim Kovalev
