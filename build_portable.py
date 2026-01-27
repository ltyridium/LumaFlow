"""
LumaFlow 免安装压缩包构建脚本
打包成 zip 格式，解压即用
"""
import os
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path

# Import metadata for version info
sys.path.insert(0, os.path.dirname(__file__))
from core.metadata import APP_METADATA

def clean_build():
    """清理之前的构建文件"""
    dirs_to_clean = ['build', 'dist']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"清理 {dir_name}...")
            shutil.rmtree(dir_name)

def build_exe():
    """使用 PyInstaller 构建可执行文件"""
    print("开始构建可执行文件...")

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--name=LumaFlow',
        '--icon=resources/icons/icon.png' if os.path.exists('resources/icons/icon.png') else '',
        '--windowed',
        '--onefile',  # 修改为单文件输出
        '--add-data=resources;resources',
        '--hidden-import=PySide6.QtCore',
        '--hidden-import=PySide6.QtGui',
        '--hidden-import=PySide6.QtWidgets',
        '--hidden-import=pyqtgraph',
        '--hidden-import=numpy',
        '--hidden-import=pandas',
        '--hidden-import=numba',
        '--hidden-import=scipy',
        '--hidden-import=scipy.fft',
        '--hidden-import=scipy.signal',
        '--hidden-import=scipy.ndimage',
        '--hidden-import=scipy.interpolate',
        '--hidden-import=scipy._lib',
        '--hidden-import=scipy.special',
        '--hidden-import=scipy._cyutility',
        '--hidden-import=librosa',
        '--hidden-import=soundfile',
        '--hidden-import=matplotlib',
        '--hidden-import=matplotlib.pyplot',
        '--hidden-import=matplotlib.cm',
        '--hidden-import=matplotlib.colors',
        '--hidden-import=serial',
        '--hidden-import=vlc',
        '--hidden-import=requests',
        '--hidden-import=PIL',
        '--exclude-module=matplotlib.tests',
        '--exclude-module=numpy.tests',
        '--exclude-module=pandas.tests',
        '--exclude-module=tkinter',
        '--exclude-module=IPython',
        '--exclude-module=jupyter',
        # '--strip',  # REMOVED - Corrupts .pyd files on Windows
        '--noupx',
        'main.py'
    ]

    subprocess.run(cmd, check=True)

def create_readme():
    """创建使用说明"""
    readme = f"""LumaFlow 免安装版

使用方法:
1. 解压此压缩包到任意目录
2. 双击 LumaFlow.exe 运行

系统要求:
- Windows 10/11 64位
- 需要安装 VLC Media Player (https://www.videolan.org) 并添加到系统 PATH
- 需要安装 FFmpeg (https://ffmpeg.org/download.html) 并添加到系统 PATH

注意事项:
- 首次运行可能需要几秒钟启动时间
- 某些杀毒软件可能误报，请添加信任
- 不要删除程序目录下的其他文件

版本: {APP_METADATA['version']}
作者: {APP_METADATA['author']}
"""
    # Create dist directory if it doesn't exist
    os.makedirs('dist', exist_ok=True)
    with open('dist/README.txt', 'w', encoding='utf-8') as f:
        f.write(readme)

def create_zip():
    """创建压缩包"""
    print("创建压缩包...")

    zip_name = f'LumaFlow_Portable_v{APP_METADATA["version"]}.zip'

    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add the executable
        exe_path = Path('dist/LumaFlow.exe')
        if exe_path.exists():
            zipf.write(exe_path, 'LumaFlow.exe')

        # Add README
        readme_path = Path('dist/README.txt')
        if readme_path.exists():
            zipf.write(readme_path, 'README.txt')

    print(f"压缩包已创建: {zip_name}")
    print(f"大小: {os.path.getsize(zip_name) / 1024 / 1024:.1f} MB")

def main():
    print("LumaFlow 免安装压缩包构建工具")
    print("=" * 50)

    # 检查 PyInstaller
    try:
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--version'], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("错误: 未安装 PyInstaller")
        print("请运行: pip install pyinstaller")
        return 1

    # 清理
    clean_build()

    # 构建
    build_exe()

    # 创建说明文件
    create_readme()

    # 打包
    create_zip()

    print("\n构建完成!")
    print(f"分发文件: LumaFlow_Portable_v{APP_METADATA['version']}.zip")

    return 0

if __name__ == '__main__':
    sys.exit(main())
