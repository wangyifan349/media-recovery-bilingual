"""Choose the GUI language explicitly; default is Chinese. 可显式选择语言，默认中文。"""

import argparse

if __name__ == "__main__":
    from app import launch

    parser = argparse.ArgumentParser(description="Media Recovery / 媒体恢复")
    parser.add_argument("--language", choices=("en", "zh"), default="zh")
    launch(parser.parse_args().language)
