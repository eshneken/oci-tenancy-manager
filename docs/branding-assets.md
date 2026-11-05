# Atlas branding assets

30 October 2026. [Instance branding settings](reference/application-settings.md#instance-branding)
keep this deployment's public identity separate from internal OTM identifiers.

| App asset | Source and preparation |
| --- | --- |
| [Horizontal wordmark](../frontend/public/branding-assets/atlas-wordmark.png) | User-provided `atlas.png`; transparent crop and resize to640×175PNG; navy sign-in/sidebar. |
| [Compact browser icon](../frontend/public/branding-assets/atlas-icon.png) | User-provided `atlas extended.png`; transparent crop and resize to256×137PNG; browser icon. |

The supplied colors, lettering and texture are retained. Alpha transparency is preserved; the
background shown behind the mark is the app's navy surface. No recoloring or new logo concept
was needed. Original files remain privately preserved in `reference/branding/atlas-originals/`.
The asset directory is public and contains only reviewed raster artwork, not documentation or
private source files. PNG filenames are stable; deployment configuration chooses the assets.

The image-generation skill was used in built-in edit/generate mode to explore smoother alternatives.
The prompt asked to preserve the cloud/circuit/red-oval identity and exact Atlas white wordmark,
remove speckling and use a transparent background. Those candidates did not materially improve
the supplied artwork and were not selected; the final assets are resized supplied originals.
Mechanical crop/downscale used macOS image tools. No Python image editing was used.

Validated responsive captures at1280,390and320pixels cover sign-in and authenticated navigation.
The configured display name supplies accessible image text and plain-text fallback.
