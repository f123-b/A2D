# `.a2d` Container v1

## Container
ZIP-compatible package.

## Required files
- `manifest.json`
- `model.json`
- `buffers/geometry.bin`

## Rules
- Binary numeric representation is little-endian.
- Buffer views are 4-byte aligned.
- Large numerical arrays MUST NOT be stored as JSON arrays.
- Texture files should be atlas-packed.
- Unknown optional files must be ignored by readers.

## Manifest minimum
```json
{
  "containerVersion": 1,
  "model": "model.json",
  "entryBuffers": ["buffers/geometry.bin"]
}
```
