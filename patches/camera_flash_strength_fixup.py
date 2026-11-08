# SPDX-FileCopyrightText: 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0

"""
camera.qcom.so fixup for the A15 camx torch strength ceiling.

ColorOS 15's camx initializes FlashInfoStrengthMaximumLevel = 164 and the
default strength level = 3 unconditionally. ColorOS 16 gates the 164 behind
GetBooleanConfiguration("FlashLED", "ThreeLED") and uses 4 for every other
device. giuliac is a dual-LED device (DualLedConfig), so stock ColorOS 16
exposes exactly four torch strength levels, matching the FlashLightCurrent
table (38; 50; 75; 100).

This patch replaces the hardcoded 164 with 4, reproducing the ColorOS 16
dual-LED behavior:

    mov  x2, #0xa4           ; 164      -> mov x2, #4
    movk x2, #0x3, lsl #32   ; default 3 (unchanged)
    str  x2, [x19, #0x3350]  ; max @0x3350, default @0x3354

The patch is anchored on the stock instruction pair, which is unique within
the blob, and is idempotent: re-running extraction over an already patched
blob is a no-op.

Stock blob: ColorOS 15 PKG110_COS_15.0.0.840
    sha256 38cf5d8d6a357dac2b9e3a03eaa33b6402081ecaef174f0a4c26b0ca5bb50dd9
"""

from hashlib import sha256
from pathlib import Path
from typing import Final

# Instructions leading up to and including the max/default strength
# initialization, as emitted by the stock A15 camx build.
_STOCK_SEQUENCE: Final = bytes.fromhex(
    "0f2c40f9"  # ldr    x15, [x0, #0x58]
    "11338052"  # mov    w17, #0x198
    "d00243b9"  # ldr    w16, [x22, #0x300]
    "821480d2"  # mov    x2, #0xa4
    "6200c0f2"  # movk   x2, #0x3, lsl #32
    "41ebffb0"  # adrp   x1, 0x175000
    "21a82f91"  # add    x1, x1, #0xbea
    "193eb19b"  # umaddl x25, w16, w17, x15
)

# Narrower anchor used when the compiler emits a slightly different
# surrounding sequence: mov x2, #0xa4 / movk x2, #0x3, lsl #32.
_STOCK_PAIR: Final = bytes.fromhex("821480d26200c0f2")
_PATCHED_PAIR: Final = bytes.fromhex("820080d26200c0f2")

_STOCK_INSN: Final = bytes.fromhex("821480d2")  # mov x2, #0xa4 (164)
_PATCHED_INSN: Final = bytes.fromhex("820080d2")  # mov x2, #4
_PATCH_OFFSET: Final = 12

_STOCK_SHA256: Final = (
    "38cf5d8d6a357dac2b9e3a03eaa33b6402081ecaef174f0a4c26b0ca5bb50dd9"
)


class CameraFlashStrengthFixupError(RuntimeError):
    pass


def _find_patch_offset(blob: bytes) -> int:
    """Return the file offset of the strength maximum instruction."""

    count = blob.count(_STOCK_SEQUENCE)
    if count > 1:
        raise CameraFlashStrengthFixupError(
            f"camera.qcom.so: strength initialization sequence found {count} "
            "times (expected at most 1)"
        )
    if count == 1:
        return blob.index(_STOCK_SEQUENCE) + _PATCH_OFFSET

    count = blob.count(_STOCK_PAIR)
    if count > 1:
        raise CameraFlashStrengthFixupError(
            f"camera.qcom.so: strength instruction pair found {count} times "
            "(expected at most 1)"
        )
    if count == 1:
        return blob.index(_STOCK_PAIR)

    raise CameraFlashStrengthFixupError(
        "camera.qcom.so: strength initialization sequence not found "
        f"(stock sha256 {sha256(blob).hexdigest()})"
    )


def patch_camera_flash_strength(blob: bytes) -> bytes:
    """Cap the hardcoded torch strength maximum level at 4."""

    if blob.count(_PATCHED_PAIR) == 1 and blob.count(_STOCK_PAIR) == 0:
        # Already patched by a previous extraction.
        return blob

    offset = _find_patch_offset(blob)
    if blob[offset : offset + 4] != _STOCK_INSN:
        raise CameraFlashStrengthFixupError(
            f"camera.qcom.so: instruction at {offset:#x} is "
            f"{blob[offset:offset + 4].hex()}, expected {_STOCK_INSN.hex()}"
        )

    patched = bytearray(blob)
    patched[offset : offset + 4] = _PATCHED_INSN
    return bytes(patched)


def patch_camera_flash_strength_file(file_path: str) -> None:
    path = Path(file_path)
    try:
        patched = patch_camera_flash_strength(path.read_bytes())
    except CameraFlashStrengthFixupError as e:
        raise CameraFlashStrengthFixupError(f"{file_path}: {e}") from e
    path.write_bytes(patched)
