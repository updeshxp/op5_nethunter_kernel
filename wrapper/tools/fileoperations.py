import os
import sys
import shutil
import requests
from typing import List
import messages as msg


def ucopy(src: str, dst: str, exceptions: List[str] = []) -> None:
    """A universal method to copy files into desired destinations.

    :param str src: Source path.
    :param str dst: Destination path.
    :param list exceptions: Elements that will not be removed.
    """
    # for a directory (it's contents)
    if os.path.isdir(src):
        if not os.path.isdir(dst):
            os.mkdir(dst)
        contents = os.listdir(src)
        for e in contents:
            # do not copy restricted files
            if e not in exceptions and e != src:
                src_e = os.path.join(src, e)
                dst_e = os.path.join(dst, e)
                if os.path.isdir(src_e):
                    shutil.copytree(src_e, dst_e)
                elif os.path.isfile(src_e):
                    shutil.copy(src_e, dst_e)
    # for a single file
    elif os.path.isfile(src):
        shutil.copy(src, dst)


def download(url: str) -> None:
    """A simple file downloader.

    :param str url: URL to the file.
    """
    file = url.split("/")[-1]
    msg.note(f"Downloading {file} ..")
    print(f"      URL: {url}")
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): 
                    f.write(chunk)
    except Exception:
        msg.error("Download failed.")
    msg.done("Done!")
