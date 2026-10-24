"""Small declarative board registry shared by GUI and CLI."""
from dataclasses import dataclass
from pathlib import Path
import os

PROJECT_DIR = Path(__file__).resolve().parents[2]
BASELINE_COMMIT = '65db64b4890c399b8fcc9cc6a3d002c2b86e4706'

@dataclass(frozen=True)
class BoardProfile:
    key: str
    name: str
    pcb: str
    pcbrev: str
    flavour: str
    flash_size: int = 512 * 1024
    bootloader_size: int = 32 * 1024
    flash_address: str = '0x08000000'
    dfu_id: str = '0483:df11'
    hse_hz: int | None = None

PROFILES = {
    'saolalink-v1': BoardProfile('saolalink-v1', 'SaolaLink V1', 'X7', 'SAOLALINK_V1', 'saolalinkv1', hse_hz=12000000),
    'saolalink-devebox': BoardProfile('saolalink-devebox', 'SaolaLink DevEBox 8MHz (EdgeTX USB)', 'X7', 'SAOLALINK_V1', 'saolalinkv1', hse_hz=8000000),
    'pocket': BoardProfile('pocket', 'RadioMaster Pocket (reference)', 'X7', 'POCKET', 'pocket'),
}

@dataclass(frozen=True)
class AppConfig:
    source: Path
    builds: Path
    toolchain: Path | None = None

    @classmethod
    def default(cls):
        bundled = PROJECT_DIR / '.tools/arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi/bin'
        configured = os.environ.get('ARM_TOOLCHAIN_DIR')
        return cls(
            Path(os.environ.get('EDGETX_DIR', str(PROJECT_DIR / 'edgetx'))).expanduser().resolve(),
            Path(os.environ.get('SAOLALINK_BUILD_DIR', str(PROJECT_DIR / 'build'))).expanduser().resolve(),
            Path(configured).expanduser().resolve() if configured else (bundled if bundled.is_dir() else None),
        )

    def build_dir(self, profile, mode):
        if mode not in ('Debug', 'Release'):
            raise ValueError('Build type must be Debug or Release')
        return self.builds / profile.key / mode.lower()
