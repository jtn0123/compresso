# Encoding Guide — Getting the Smallest Files

Compresso's purpose is reclaiming storage from inefficiently-encoded media. This guide covers the encoder choices that serve that goal — and the ones that quietly work against it.

## TL;DR

- **Use software encoders.** `libx265` (HEVC) or `libsvtav1` (AV1). They produce the smallest files at any given visual quality and are Compresso's defaults.
- **Software encoders run on any CPU** — Intel, AMD, or Apple Silicon; Linux (Docker), macOS, or Windows. No GPU, driver, or device passthrough required.
- **Hardware encoders are a LAST RESORT.** NVENC, QSV, VAAPI, and VideoToolbox are built for real-time speed, not compression efficiency. At the same visual quality they produce substantially larger files — often tens of percent — which defeats the purpose of a storage-reduction run.
- **Hardware *decoding* is fine.** Decoding the source with a GPU is quality-neutral; only the *encoder* choice affects output size and quality.

## Recommended encoders by target codec

| Target codec | Use this encoder | Notes |
|---|---|---|
| HEVC (H.265) | `libx265` | The safe default: broad device compatibility, mature, excellent efficiency |
| AV1 | `libsvtav1` | Best compression; check your playback devices support AV1 first |
| H.264 (AVC) | `libx264` | Only if a playback device requires H.264 — HEVC/AV1 save far more space |

All three are the built-in defaults when you leave the encoder field empty in the Encoding Presets plugin.

## Starting points for quality settings

The right values depend on your content and your eyes — validate with the A/B preview (VMAF/SSIM scores) before approving replacements at scale.

| Encoder | CRF starting point | Preset starting point | Notes |
|---|---|---|---|
| `libx265` | 22–24 | `medium`, or `slow` if you can afford the time | Lower CRF = better quality, larger files (0–51 scale) |
| `libsvtav1` | 28–32 | `medium` (maps to SVT preset 5) | AV1's CRF scale (0–63) reads higher than x265's for similar quality |
| `libx264` | 20–23 | `medium` or `slow` | Least efficient of the three — prefer HEVC/AV1 |

Two levers matter:

- **CRF** sets the quality target. Raise it a little to save more space; lower it if the A/B preview shows artifacts.
- **Preset** sets how hard the encoder works. Slower presets produce smaller files *at the same quality* — pure gain if you have the CPU time. For a long-running library job where throughput isn't urgent, `slow` is worth it.

## When hardware encoding is acceptable

Hardware encoders (NVENC, QSV, VAAPI, VideoToolbox) exist for one reason: speed. That makes them appropriate for:

- Real-time or near-real-time transcoding (streaming servers — a different job than Compresso's)
- Throwaway encodes where output size doesn't matter
- Situations where an encode simply must finish faster than the CPU allows, and the storage cost is accepted knowingly

For a permanent, library-wide re-encode, they are the wrong tool. If you're considering one because software encoding feels slow, reach for these first:

1. A faster software preset (`fast`/`faster`) still beats hardware encoders on size
2. More worker machines (Compresso supports multi-machine links)
3. Patience — the encode runs once; the storage savings last forever

## Validating your settings

Before letting any preset loose on a library:

1. Run a handful of representative files through with approval mode on.
2. Use the A/B preview to compare source vs. encoded output side by side, and check the VMAF/SSIM scores.
3. Compare file sizes — if savings are thin, raise CRF or pick a more efficient target codec before scaling up.

For a full production rollout process, see the [20 TB Media Compression Runbook](20TB_MEDIA_COMPRESSION_RUNBOOK.md).
