# KARUSELKA

Fast camera turntable rig for Blender. Pick an object, press **Create Rig** —
a camera orbits it on linear keyframes, ready to scrub or render as a showreel
turntable.

Pairs with [LAMPOCHKA](https://github.com/abyrvalg379/lampochka):
light preset + KARUSELKA turntable = model showcase in two minutes.

## Features

- One click: rig + keyframes, live immediately
- Two modes: **Camera** orbits the object, or **Object** spins on its axis
  with a static camera. In Object mode the model's hierarchy root is parented
  to a `KARUSELKA_Empty` (if the target already has a parent, that parent
  chain root is used); Remove Rig restores the hierarchy
- The rig camera becomes the active scene camera (Numpad 0 / render);
  Remove Rig puts your previous active camera back
- Constant rotation speed — interpolation is forced to LINEAR
  (bezier easing is the classic turntable mistake)
- Auto radius = object size × Margin (default 2.5, adjustable) — never
  right up against the model
- Camera settings right in the panel: Lens, DoF, near/far clip — edits
  apply to the rig camera live
- Every Create Rig starts from fresh defaults; the **Keep Settings**
  checkbox reuses the previous camera's lens/DoF/clips instead
- Auto near/far clip at a fixed 1000:1 ratio — small and huge models
  stay in view without depth-buffer artifacts
- **Render Turntable** — non-blocking animation render to `//turntable/`,
  warns if the scene has no lights
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
| Mode | Camera = orbit around the object; Object = the object spins, camera static |
| Target | object to turntable (falls back to the active object) |
| Camera | yours, or auto-created |
| Frames | frames per full revolution; fps comes from the scene |
| Rounds | revolutions, fractional allowed |
| Radius | orbit distance; 0 = auto (object size × Margin) |
| Margin | auto-radius multiplier (default 2.5) |
| Height | camera height relative to the object center |
| Dir | rotation direction viewed from above |
| Lens / DoF / Clip | rig camera settings, applied live |
| Keep Settings | rebuild inherits the previous camera instead of defaults |
| Output | render path, default `//turntable/` |

### Notes

- Object Spin parents the model's hierarchy root to a `KARUSELKA_Empty`;
  Remove Rig unparents it again with the world transform preserved.
- Render Turntable sets the scene frame range to `1..N` and leaves it visible
  in the timeline; engine, samples and format settings are not touched.
- With your own camera KARUSELKA aims it and (in Camera mode) parents it to
  the pivot; Remove Rig detaches it again (keeps the world transform).
- Keyframes live on the pivot/spin empty (`rotation_euler.z`, frame 1 →
  frame N); tweak speed by editing Frames/Rounds and re-running Create Rig.

## License

GPL-3.0-or-later — see [LICENSE](LICENSE). © Maksim Kovalev
