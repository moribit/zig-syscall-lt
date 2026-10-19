#!/usr/bin/env python3
"""Download references to a temporary directory; verify the reviewed versions."""
import argparse,hashlib,subprocess as sp,tarfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();a.directory.mkdir(parents=True,exist_ok=True)
references=[('tlpi-book.tar.gz','https://man7.org/tlpi/code/download/tlpi-260523-book.tar.gz','698a09c7ff428d92e81d3a695a1d855955ebf328c4458b70d1d3d4541bc2fb65'),('slides.pdf','https://man7.org/training/download/lusp_epoll_slides-mkerrisk-man7.org.pdf','e691d99157d2d091623e3c274f0dae4dd53fd85b6890639dce920aabf092d4e0'),('tlpi.tar.gz','https://man7.org/tlpi/code/download/tlpi-260523-dist.tar.gz','7bb1155f6a90f382e18eaf961133d4f3b0583afd278416fba97406bdb0c606e2')]
for name,url,sha in references:
 path=a.directory/name
 if not path.exists():sp.run(['curl','-fSL',url,'-o',str(path)],check=True)
 assert hashlib.sha256(path.read_bytes()).hexdigest()==sha,'Reference changed; review rather than silently replacing its hash'
for archive in ['tlpi.tar.gz','tlpi-book.tar.gz']:
 with tarfile.open(a.directory/archive) as tar:
  names=tar.getnames();assert not any(n.endswith('/altio_speed.c') for n in names);print(archive+': no altio_speed.c')
print('All reference hashes match the reviewed versions. Lecture/archive are not redistributed.')
