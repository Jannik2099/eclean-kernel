# vim:fileencoding=utf-8
# (c) 2011-2020 Michał Górny <mgorny@gentoo.org>
# Released under the terms of the 2-clause BSD license.

import os.path
import typing

from glob import glob
from pathlib import Path

from ecleankernel.file import KernelFileType, GenericFile, KernelImage
from ecleankernel.kernel import Kernel


class StdLayout(object):
    """
    Standard /boot layout used by pre-systemd-boot bootloaders

    A standard /boot layout presuming that all kernel files are placed
    directly in /boot directory.
    """

    def find_kernels(self,
                     exclusions: typing.List[str] = [],
                     boot_directory: Path = Path('/boot'),
                     module_directory: Path = Path('/lib/modules')
                     ) -> typing.List[Kernel]:
        """
        Find all files and directories related to installed kernels

        Find all kernel files and related data and return a list
        of `Kernel` objects.  `exclusions` specifies kernel parts
        to ignore.  `boot_directory` and `module_directory` specify
        paths to find kernels in.
        """

        globs = [
            (KernelFileType.KERNEL, f'{boot_directory}/vmlinuz-'),
            (KernelFileType.KERNEL, f'{boot_directory}/vmlinux-'),
            (KernelFileType.KERNEL, f'{boot_directory}/kernel-'),
            (KernelFileType.KERNEL, f'{boot_directory}/bzImage-'),
            (KernelFileType.SYSTEM_MAP, f'{boot_directory}/System.map-'),
            (KernelFileType.CONFIG, f'{boot_directory}/config-'),
            (KernelFileType.INITRAMFS, f'{boot_directory}/initramfs-'),
            (KernelFileType.INITRAMFS, f'{boot_directory}/initrd-'),
            (KernelFileType.MODULES, f'{module_directory}/'),
        ]

        prev_paths: typing.Set[str] = set()

        kernels: typing.Dict[str, Kernel] = {}
        for cat, g in globs:
            if cat.value in exclusions:
                continue
            for m in glob('%s*' % g):
                kv = m[len(g):]
                if cat == KernelFileType.INITRAMFS:
                    if kv.endswith('.img'):
                        kv = kv[:-4]
                    elif kv.endswith('.img.old'):
                        kv = kv[:-8] + '.old'
                elif cat == KernelFileType.MODULES:
                    if any(os.path.samefile(x, m) for x in prev_paths):
                        continue

                file_obj: GenericFile
                if cat == KernelFileType.KERNEL:
                    file_obj = KernelImage(Path(m))
                else:
                    file_obj = GenericFile(Path(m), cat)

                prev_paths.add(m)
                newk = kernels.setdefault(kv, Kernel(kv))
                try:
                    setattr(newk, cat.value, file_obj)
                except KeyError:
                    raise SystemError('Colliding %s files: %s and %s'
                                      % (cat.value,
                                         m,
                                         getattr(newk, cat.value)))

                if cat == KernelFileType.MODULES:
                    builddir = os.path.join(m, 'build')
                    if os.path.isdir(builddir):
                        newk.build = GenericFile(Path(builddir),
                                                 KernelFileType.BUILD)

                    if '%s.old' % kv in kernels:
                        kernels['%s.old' % kv].modules = newk.modules
                        if newk.build:
                            kernels['%s.old' % kv].build = newk.build
                elif cat == KernelFileType.KERNEL:
                    assert isinstance(file_obj, KernelImage)
                    realkv = file_obj.internal_version
                    moduledir = os.path.join('/lib/modules', realkv)
                    builddir = os.path.join(moduledir, 'build')
                    if ('modules' not in exclusions
                            and os.path.isdir(moduledir)):
                        newk.modules = GenericFile(Path(moduledir),
                                                   KernelFileType.MODULES)
                        prev_paths.add(moduledir)
                    if ('build' not in exclusions
                            and os.path.isdir(builddir)):
                        newk.build = GenericFile(Path(builddir),
                                                 KernelFileType.BUILD)
                        prev_paths.add(builddir)

        # fill .old files
        for k in kernels.values():
            if '%s.old' % k.version in kernels:
                oldk = kernels['%s.old' % k.version]
                # it seems that these are renamed .old sometimes
                if not oldk.systemmap and k.systemmap:
                    oldk.systemmap = k.systemmap
                if not oldk.config and k.config:
                    oldk.config = k.config

        return list(kernels.values())