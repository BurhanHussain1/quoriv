"""Permission and safety layer.

Every tool call passes through the guard in this package before execution.
Supports four modes (read-only, ask, auto, yolo), a remembered allowlist
for "always allow" patterns, and unconditional path protection.

Path protection (.env, ~/.ssh, etc.) is enforced in every mode, including
yolo. There is no way to bypass it through configuration.
"""
