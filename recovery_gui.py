"""Compatibility entry point. 兼容旧启动路径；实际界面见 app.py。"""

from app import RecoveryApp, launch

__all__ = ["RecoveryApp", "launch"]

if __name__ == "__main__":
    launch()
