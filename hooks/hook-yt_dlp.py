"""PyInstaller가 yt-dlp의 동적 extractor/postprocessor 모듈을 빠뜨리지 않게 한다."""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


hiddenimports = collect_submodules("yt_dlp")
datas = collect_data_files("yt_dlp")

